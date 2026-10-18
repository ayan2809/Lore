"""Human-in-the-loop actions (plan section 8, "Human in the loop").

Lifecycle:  proposed --edit--> proposed --approve--> sent | blocked | failed      (or: rejected)

- `propose()` is called by the Responder's `propose_action` tool. Nothing is sent.
- `approve()` is the only place anything leaves the system. A Slack post is first checked by
  `policy.check_post_audience` (everyone in the channel must be allowed to see every cited source).
- Rollbacks are always simulated. Missing Slack/GitHub config also means "simulated", so the
  demo works offline.
- The Slack webhook and GitHub repo come from settings, never from the action: the model can
  choose the text but not where it goes.

The `Action` model has no spare field for notes, so a human-readable note (why it was blocked,
why it was simulated, why it failed) is stored in `Action.blocked_reason`.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx

from lore.config import Settings, get_settings
from lore.db import GraphLike, load_query
from lore.models import Action, ActionKind
from lore.observability import log_event

_ACTIONS: dict[str, Action] = {}  # in-process registry; the graph copy is for audit/memory
_graph: GraphLike | None = None  # set by configure(); used by propose() to save the node

HTTP_TIMEOUT_S = 5.0
MAX_ATTEMPTS = 3
BACKOFF_S = 0.5  # waits 0.5s, 1s, ... between attempts
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests inject httpx.MockTransport here


class ActionNotFound(KeyError):
    pass


class ActionStateError(ValueError):
    """The action is not in a state where this operation makes sense (e.g. already sent)."""


def configure(graph: GraphLike | None) -> None:
    """Tell this module which graph to save Action nodes into (None = memory only)."""
    global _graph
    _graph = graph


def get(action_id: str) -> Action:
    try:
        return _ACTIONS[action_id]
    except KeyError:
        raise ActionNotFound(action_id) from None


def for_investigation(investigation_id: str) -> list[Action]:
    return [a for a in _ACTIONS.values() if a.investigation_id == investigation_id]


def register(action: Action) -> Action:
    """Add an existing Action (used when a replay re-emits a recorded proposal)."""
    _ACTIONS[action.id] = action
    return action


def propose(
    investigation_id: str,
    kind: ActionKind,
    target: str,
    text: str,
    cited_ids: list[str],
    title: str | None = None,
) -> Action:
    action = Action(
        id=f"action:{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        kind=kind,
        target=target,
        title=title,
        text=text,
        cited_ids=list(cited_ids),
        simulated=(kind == "rollback"),
    )
    register(action)
    _save(action, _graph)
    return action


def edit(action_id: str, text: str, cited_ids: list[str] | None = None) -> Action:
    """Change the text, and optionally drop citations (you can only remove, never add)."""
    action = get(action_id)
    if action.status in ("sent", "rejected", "approved"):
        raise ActionStateError(f"cannot edit an action that is {action.status}")
    action.text = text
    if cited_ids is not None:
        action.cited_ids = [c for c in action.cited_ids if c in set(cited_ids)]
    action.status = "proposed"  # an edited blocked/failed action can be tried again
    action.blocked_reason = None
    _save(action, _graph)
    return action


def reject(action_id: str) -> Action:
    action = get(action_id)
    if action.status in ("sent", "rejected"):
        raise ActionStateError(f"cannot reject an action that is {action.status}")
    action.status = "rejected"
    _save(action, _graph)
    return action


async def approve(
    action_id: str, graph: GraphLike | None = None, settings: Settings | None = None
) -> Action:
    """Run the policy check, then send (or simulate) the action. Never raises on send errors."""
    settings = settings or get_settings()
    action = get(action_id)
    if action.status not in ("proposed", "failed"):
        raise ActionStateError(f"cannot approve an action that is {action.status}")

    if action.kind in ("slack_post", "github_issue"):
        reason = await _audience_problem(action, graph)
        if reason:
            action.status = "blocked"
            action.blocked_reason = reason
            log_event(event="action_blocked", action_id=action.id, reason=reason)
            await _save_async(action, graph)
            return action

    action.status = "approved"
    action.blocked_reason = None
    try:
        await _send(action, settings)
    except Exception as exc:  # the action stays visible with the error, so a human can retry
        action.status = "failed"
        action.blocked_reason = f"{type(exc).__name__}: {exc}"
    log_event(event="action_" + action.status, action_id=action.id, kind=action.kind,
              simulated=action.simulated)
    await _save_async(action, graph)
    return action


# ------------------------------------------------------------------------------------ internals


async def _audience_problem(action: Action, graph: GraphLike | None) -> str | None:
    """Return a reason string if the post must be blocked, else None. Fails closed."""
    from lore import policy  # imported here so tests can monkeypatch lore.policy

    try:
        if action.kind == "github_issue":
            decision = await asyncio.to_thread(
                policy.check_issue_citations, graph, action.cited_ids
            )
        else:
            channel_id = "channel:" + action.target.lstrip("#")
            decision = await asyncio.to_thread(
                policy.check_post_audience, graph, channel_id, action.cited_ids
            )
    except Exception as exc:
        return f"Policy check could not run ({type(exc).__name__}), so the post was not sent."
    return None if decision.allowed else (decision.reason or "Blocked by policy.")


async def _send(action: Action, settings: Settings) -> None:
    """Fill in status/simulated/result_url on the action. Raises on real send failures."""
    if action.kind == "rollback":
        action.simulated = True
        action.status = "sent"
        action.blocked_reason = "Simulated: Lore never runs rollbacks, it only proposes them."
    elif action.kind == "slack_post":
        if not settings.slack_webhook_url:
            _mark_simulated(action, "LORE_SLACK_WEBHOOK_URL is not set")
            return
        await _request("POST", settings.slack_webhook_url, json={"text": action.text})
        action.status = "sent"
    elif action.kind == "github_issue":
        if not (settings.github_token and settings.github_repo):
            _mark_simulated(action, "LORE_GITHUB_TOKEN or LORE_GITHUB_REPO is not set")
            return
        title = action.title or action.text.splitlines()[0][:80]
        resp = await _request(
            "POST",
            f"https://api.github.com/repos/{settings.github_repo}/issues",
            json={"title": title, "body": action.text},
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        action.result_url = resp.json().get("html_url")
        action.status = "sent"


def _mark_simulated(action: Action, why: str) -> None:
    action.simulated = True
    action.status = "sent"
    action.blocked_reason = f"Simulated, nothing was sent: {why}."


async def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """HTTP call with a timeout and retries (backoff). 4xx errors are not retried."""
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, transport=HTTP_TRANSPORT) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code < 400:
                    return resp
                last = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code < 500 and resp.status_code != 429:
                    break  # our fault (bad token, bad repo): retrying will not help
            except httpx.TransportError as exc:  # timeout, connection refused, ...
                last = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(BACKOFF_S * 2**attempt)
    raise last or RuntimeError("request failed")


def _save(action: Action, graph: GraphLike | None) -> None:
    """Persist the Action node. Memory-only if there is no graph; never raises."""
    if graph is None:
        return
    try:
        graph.write(
            load_query("action_upsert"),
            {
                "id": action.id,
                "investigation_id": action.investigation_id,
                "kind": action.kind,
                "target": action.target,
                "title": action.title,
                "text": action.text,
                "cited_ids": action.cited_ids,
                "status": action.status,
                "blocked_reason": action.blocked_reason,
                "result_url": action.result_url,
                "simulated": action.simulated,
            },
        )
    except Exception as exc:
        log_event(event="action_save_failed", action_id=action.id, error=str(exc))


async def _save_async(action: Action, graph: GraphLike | None) -> None:
    await asyncio.to_thread(_save, action, graph or _graph)
