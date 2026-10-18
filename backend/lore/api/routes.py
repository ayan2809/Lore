"""Every HTTP endpoint (docs/PROJECT_CONTEXT.md section 6). Prefix: /api.

Rules this file follows:
- The viewer comes from `current_viewer()` (the signed cookie). Request bodies and query strings
  never carry a viewer.
- Runs and their actions are only visible to the viewer who started them.
- Work that belongs to other modules (supervisor, ask, graph_view, memory, policy) is imported
  inside the route, so the API can start even when one of them is unfinished.
"""

# ruff: noqa: B008  (FastAPI's `Depends(...)` as a default value is the standard pattern)

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from lore import actions, replay
from lore.api import deps, runs
from lore.api.ratelimit import rate_limit
from lore.api.runs import Run, RunRegistry
from lore.api.session import current_persona, current_viewer, set_persona
from lore.config import Settings, get_settings
from lore.db import GraphLike
from lore.models import (
    Action,
    AskAnswer,
    Claim,
    GraphMode,
    GraphView,
    Persona,
    Report,
    RunSummary,
    Viewer,
)
from lore.observability import Timer, log_event
from lore.permissions import PERSONAS
from lore.tools import ToolContext

router = APIRouter(prefix="/api")

# Shown when the graph is down, so the UI can still offer the replay demo.
FALLBACK_ALERTS = [
    {"id": "A-3001", "name": "checkout p99 latency > 3s", "symptom": "checkout p99 latency > 3s",
     "service": "svc:checkout", "started_at": 1791927000},
    {"id": "A-3002", "name": "dispatch assignment latency > 5s",
     "symptom": "dispatch assignment latency > 5s", "service": "svc:dispatch",
     "started_at": 1792532400},
]


# ------------------------------------------------------------------------------ request bodies


class SessionBody(BaseModel):
    persona: str


class StartBody(BaseModel):
    alert_id: str
    mode: GraphMode = "graph"
    replay: bool = False


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: GraphMode = "graph"


class FeedbackBody(BaseModel):
    confirmed: bool
    note: str | None = Field(default=None, max_length=1000)


class EditBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    # Optional: the citations to keep. Lets a reviewer drop a restricted source (FIX_LOG F-09).
    cited_ids: list[str] | None = None


# ------------------------------------------------------------------------------ helpers


def _own_run(registry: RunRegistry, run_id: str, viewer: Viewer) -> Run:
    """404 for unknown runs AND for other people's runs (events contain permitted-only content)."""
    run = registry.get(run_id)
    if run is None or run.viewer_id != viewer.id:
        raise HTTPException(404, "investigation not found")
    return run


def _own_action(registry: RunRegistry, action_id: str, viewer: Viewer) -> Action:
    try:
        action = actions.get(action_id)
    except actions.ActionNotFound:
        raise HTTPException(404, "action not found") from None
    _own_run(registry, action.investigation_id, viewer)
    return action


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


# ------------------------------------------------------------------------------ health, session


@router.get("/health")
async def health(
    request: Request,
    settings: Settings = Depends(get_settings),
    graph: GraphLike | None = Depends(deps.get_graph),
) -> dict:
    falkordb = False
    if graph is not None:
        try:
            await asyncio.wait_for(asyncio.to_thread(graph.ro, "RETURN 1"), 2)
            falkordb = True
        except Exception as exc:
            # A brand-new database has no graph yet ("empty key"): the server is up, the
            # loader just has not run (FIX_LOG F-08).
            falkordb = "empty key" in str(exc).lower()
    gemini = bool(settings.gemini_api_key)
    budget = request.app.state.budget
    return {"status": "ok", "falkordb": falkordb, "gemini": gemini,
            "replay": settings.force_replay or not gemini,
            "live_runs_left_today": budget.remaining("investigation", settings.live_runs_per_day)}


@router.get("/personas")
def personas() -> list[Persona]:
    return list(PERSONAS.values())


@router.get("/session")
def get_session(persona: str = Depends(current_persona)) -> dict:
    return {"persona": PERSONAS[persona]}


@router.post("/session")
def post_session(body: SessionBody, settings: Settings = Depends(get_settings)):
    if body.persona not in PERSONAS:
        raise HTTPException(404, f"unknown persona {body.persona!r}")
    response = JSONResponse({"persona": PERSONAS[body.persona].model_dump()})
    set_persona(response, body.persona, settings)
    return response


# ------------------------------------------------------------------------------ graph and sources


@router.get("/alerts")
async def alerts(graph: GraphLike | None = Depends(deps.get_graph)) -> list[dict]:
    if graph is None:
        return FALLBACK_ALERTS
    from lore import graph_view

    try:
        return await asyncio.to_thread(graph_view.list_alerts, graph)
    except Exception as exc:
        log_event(event="alerts_failed", error=str(exc))
        return FALLBACK_ALERTS


@router.get("/graph")
async def graph_neighbourhood(
    center: str = "svc:checkout",
    hops: int = Query(2, ge=1, le=4),
    limit: int = Query(200, ge=1, le=500),
    viewer: Viewer = Depends(current_viewer),
    graph: GraphLike | None = Depends(deps.get_graph),
) -> GraphView:
    from lore import graph_view

    ctx = ToolContext(viewer=viewer, graph=deps.require_graph(graph))
    return await asyncio.to_thread(graph_view.neighbourhood, ctx, center, hops, limit)


@router.get("/sources/{source_id:path}")
async def source(
    source_id: str,
    viewer: Viewer = Depends(current_viewer),
    graph: GraphLike | None = Depends(deps.get_graph),
):
    from lore import graph_view

    ctx = ToolContext(viewer=viewer, graph=deps.require_graph(graph))
    detail = await asyncio.to_thread(graph_view.source_detail, ctx, source_id)
    if detail is None:  # same answer for "does not exist" and "not allowed": no existence leak
        raise HTTPException(404, "source not found")
    return detail


# ------------------------------------------------------------------------------ investigations


@router.post("/investigations", dependencies=[Depends(rate_limit)])
async def start_investigation(
    request: Request,
    body: StartBody,
    persona: str = Depends(current_persona),
    viewer: Viewer = Depends(current_viewer),
    settings: Settings = Depends(get_settings),
    graph: GraphLike | None = Depends(deps.get_graph),
    llm=Depends(deps.get_llm),
    registry: RunRegistry = Depends(runs.get_registry),
) -> dict:
    use_replay = body.replay or settings.force_replay or llm is None
    replay_reason = None
    if not use_replay and not request.app.state.budget.take(
        "investigation", settings.live_runs_per_day
    ):
        # Public-URL protection (R-31): today's live runs are used up, so play the recording.
        use_replay, replay_reason = True, "daily_live_limit"
    if not use_replay:
        deps.require_graph(graph)
    run = registry.create(viewer.id, body.alert_id, body.mode, use_replay)
    log_event(event="investigation_start", investigation_id=run.id, viewer=viewer.id,
              alert_id=body.alert_id, mode=body.mode, replay=use_replay, reason=replay_reason)
    if use_replay:
        registry.start_replay(
            run, replay.find_replay(body.alert_id, persona, settings, mode=body.mode)
        )
    else:
        registry.start_live(run, viewer, llm, graph, settings)
    return {"investigation_id": run.id, "replay": use_replay, "replay_reason": replay_reason}


@router.get("/investigations/{investigation_id}/events")
async def investigation_events(
    investigation_id: str,
    viewer: Viewer = Depends(current_viewer),
    registry: RunRegistry = Depends(runs.get_registry),
):
    run = _own_run(registry, investigation_id, viewer)

    async def messages():
        async for event in run.stream():
            yield runs.sse_message(event)

    return EventSourceResponse(messages(), ping=15)


@router.get("/investigations/{investigation_id}")
def investigation(
    investigation_id: str,
    viewer: Viewer = Depends(current_viewer),
    registry: RunRegistry = Depends(runs.get_registry),
) -> dict:
    run = _own_run(registry, investigation_id, viewer)
    summary = run.summary or RunSummary(investigation_id=run.id, replay=run.replay)
    report: Report | None = run.report
    return {"report": report, "summary": summary, "actions": run.actions()}


@router.post("/investigations/{investigation_id}/feedback")
async def feedback(
    investigation_id: str,
    body: FeedbackBody,
    viewer: Viewer = Depends(current_viewer),
    graph: GraphLike | None = Depends(deps.get_graph),
    llm=Depends(deps.get_llm),
    registry: RunRegistry = Depends(runs.get_registry),
) -> dict:
    run = _own_run(registry, investigation_id, viewer)
    log_event(event="feedback", investigation_id=run.id, confirmed=body.confirmed, note=body.note)
    if run.replay:
        return {"playbook_id": None}  # replays have no Investigation node to learn from
    from lore import memory

    playbook_id = await _maybe_await(
        memory.apply_feedback(
            deps.require_graph(graph),
            investigation_id=run.graph_id or run.id,
            confirmed=body.confirmed,
            llm=llm,
        )
    )
    return {"playbook_id": playbook_id}


# ------------------------------------------------------------------------------ ask the brain


@router.post("/ask", dependencies=[Depends(rate_limit)])
async def ask_the_brain(
    request: Request,
    body: AskBody,
    settings: Settings = Depends(get_settings),
    viewer: Viewer = Depends(current_viewer),
    graph: GraphLike | None = Depends(deps.get_graph),
    llm=Depends(deps.get_llm),
) -> AskAnswer:
    from lore import ask, policy

    decision = policy.check_request(body.question)
    if not decision.allowed:  # rule-based block; the reason is shown to the user
        return AskAnswer(question=body.question, viewer_id=viewer.id, mode=body.mode,
                         refused=True, claims=[Claim(text=decision.reason or "Blocked by policy.")])
    if llm is None:
        raise HTTPException(503, "Gemini is not configured, so Ask is unavailable (no replay).")
    if not request.app.state.budget.take("ask", settings.live_asks_per_day):
        raise HTTPException(429, "Today's limit of live questions is used up (it protects the "
                                 "Gemini bill on this public demo). Please try again tomorrow.")
    with Timer() as timer:
        answer = await ask.ask(
            body.question, viewer, mode=body.mode, llm=llm, graph=deps.require_graph(graph)
        )
    log_event(event="ask", viewer=viewer.id, mode=body.mode, ms=round(timer.ms, 1),
              refused=answer.refused, cited=[s.id for s in answer.sources])
    return answer


# ------------------------------------------------------------------------------ actions


def _action_errors(fn):
    """Turn actions.py errors into HTTP errors."""
    try:
        return fn()
    except actions.ActionNotFound:
        raise HTTPException(404, "action not found") from None
    except actions.ActionStateError as exc:
        raise HTTPException(409, str(exc)) from None


@router.patch("/actions/{action_id}")
def edit_action(
    action_id: str,
    body: EditBody,
    viewer: Viewer = Depends(current_viewer),
    registry: RunRegistry = Depends(runs.get_registry),
) -> Action:
    _own_action(registry, action_id, viewer)
    return _action_errors(lambda: actions.edit(action_id, body.text, body.cited_ids))


def _public_url(request: Request, settings: Settings) -> str | None:
    """Where people open Lore: the setting, else the browser's Origin, else CloudFront's host."""
    if settings.public_url:
        return settings.public_url.rstrip("/")
    if request.headers.get("origin"):
        return request.headers["origin"].rstrip("/")
    host = request.headers.get("host")
    proto = request.headers.get("cloudfront-forwarded-proto") or request.url.scheme
    return f"{proto}://{host}" if host else None


async def _render_action(action: Action, run, graph: GraphLike | None, lore_url: str | None):
    """Readable Slack blocks / GitHub issue text from the run's report (HUMAN_REVIEW R-36).
    Returns None, so the raw text is sent, if there is no report yet or anything goes wrong:
    formatting must never block an approved action."""
    from lore import slack_format as fmt

    report = getattr(run, "report", None)
    if report is None or graph is None or action.kind not in ("slack_post", "github_issue"):
        return None
    try:
        ids = [run.alert_id, *action.cited_ids, *report.evidence_path,
               report.root_cause or "", report.people.page or "", *report.people.consult,
               *report.people.notify, *[i for c in report.claims + report.rejected_suspects
                                       for i in c.citations], *fmt._ID.findall(action.text)]
        alert_id = run.alert_id if ":" in run.alert_id else f"alert:{run.alert_id}"
        ids.append(alert_id)
        names = await asyncio.to_thread(fmt.lookup_names, graph, [i for i in ids if i])
        if action.kind == "slack_post":
            issue_url = next((a.result_url for a in run.actions()
                              if a.kind == "github_issue" and a.result_url), None)
            return fmt.build_message(report, alert_id, action.text, names,
                                     lore_url=lore_url, issue_url=issue_url)
        body = fmt.humanize(action.text, names)
        if lore_url:
            body += f"\n\n---\nDrafted by [Lore]({lore_url}) and approved by a human."
        title = fmt.humanize(action.title or action.text.splitlines()[0][:80], names)
        return {"title": title, "body": body}
    except Exception as exc:
        log_event(event="render_action_failed", action_id=action.id, error=str(exc))
        return None


@router.post("/actions/{action_id}/approve")
async def approve_action(
    request: Request,
    action_id: str,
    viewer: Viewer = Depends(current_viewer),
    settings: Settings = Depends(get_settings),
    graph: GraphLike | None = Depends(deps.get_graph),
    registry: RunRegistry = Depends(runs.get_registry),
) -> Action:
    action = _own_action(registry, action_id, viewer)
    rendered = await _render_action(action, registry.get(action.investigation_id), graph,
                                    _public_url(request, settings))
    try:
        # graph may be None: the policy check then fails closed and the post is blocked
        return await actions.approve(action_id, graph, settings, rendered)
    except actions.ActionNotFound:
        raise HTTPException(404, "action not found") from None
    except actions.ActionStateError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/actions/{action_id}/reject")
def reject_action(
    action_id: str,
    viewer: Viewer = Depends(current_viewer),
    registry: RunRegistry = Depends(runs.get_registry),
) -> Action:
    _own_action(registry, action_id, viewer)
    return _action_errors(lambda: actions.reject(action_id))
