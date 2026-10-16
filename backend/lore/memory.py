"""Agent memory in the graph (plan section 8, "Memory (Track 2)").

This is the only agent-side module that writes to FalkorDB. Three kinds of memory:
- Episodic ("what happened"): Investigation, Step and Finding nodes.
- Semantic ("what's true"): EXPERT_IN edges with valid_from/valid_to. Old facts get an end date.
- Procedural ("how to do it"): Playbook nodes learned from confirmed investigations.
Plus the `Query` trace node for every "Ask the brain" question.

Functions are synchronous (the FalkorDB client is). Async callers run them with
`asyncio.to_thread`. Every query is a parameterised file in lore/queries/memory_*.cypher.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from lore.config import Settings, get_settings
from lore.db import GraphLike, load_query
from lore.llm import LLM, user_text
from lore.models import Claim, ToolResult


def _write(graph: GraphLike, query: str, **params: Any) -> list[dict[str, Any]]:
    return graph.write(load_query(query), params).dicts()


def _read(graph: GraphLike, query: str, **params: Any) -> list[dict[str, Any]]:
    return graph.ro(load_query(query), params).dicts()


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ episodic: investigations


def start_investigation(
    graph: GraphLike,
    investigation_id: str,
    alert_id: str,
    viewer_id: str,
    mode: str,
    symptom: str = "",
    started_at: int | None = None,
) -> None:
    _write(
        graph,
        "memory_start_investigation",
        id=investigation_id,
        alert_id=alert_id,
        symptom=symptom,
        viewer_id=viewer_id,
        mode=mode,
        started_at=started_at or _now(),
    )


def finish_investigation(
    graph: GraphLike, investigation_id: str, status: str, root_cause: str | None
) -> None:
    _write(
        graph,
        "memory_finish_investigation",
        id=investigation_id,
        status=status,
        root_cause=root_cause,
        finished_at=_now(),
    )


def record_step(
    graph: GraphLike, investigation_id: str, seq: int, agent: str, result: ToolResult
) -> str:
    """Save one tool call as a Step node. Returns the step id."""
    step_id = f"step:{investigation_id}:{seq}"
    _write(
        graph,
        "memory_record_step",
        investigation_id=investigation_id,
        id=step_id,
        seq=seq,
        agent=agent,
        tool=result.tool,
        reason=result.reason,
        cypher=result.cypher,
        ms=round(result.ms, 2),
        node_ids=list(result.node_ids),
        edges=json.dumps([e.model_dump() for e in result.edges]),
        error=result.error,
        ts=_now(),
    )
    return step_id


def record_finding(
    graph: GraphLike, investigation_id: str, agent: str, claim: Claim, confidence: float
) -> str:
    """Save one validated claim as a Finding linked to the nodes it cites."""
    finding_id = f"finding:{uuid.uuid4().hex[:12]}"
    _write(
        graph,
        "memory_record_finding",
        investigation_id=investigation_id,
        id=finding_id,
        text=claim.text,
        citations=list(claim.citations),
        confidence=confidence,
        agent=agent,
        ts=_now(),
    )
    return finding_id


def read_findings(graph: GraphLike, investigation_id: str) -> list[dict[str, Any]]:
    """[{agent, text, citations, confidence}] written so far in this investigation."""
    return _read(graph, "memory_read_findings", investigation_id=investigation_id)


# ------------------------------------------------------------------ procedural: playbooks


class PlaybookDraft(BaseModel):
    """What Gemini Flash writes when it turns a confirmed investigation into a playbook."""

    name: str = Field(description="Short name, e.g. 'Config TTL change in a dependency'")
    symptom_pattern: str = Field(description="The kind of alert this playbook fits, generalised")
    steps: list[str] = Field(description="Tool names in the order to run them")


PLAYBOOK_PROMPT = """You turn a confirmed incident investigation into a reusable playbook.
Generalise: do not name specific services, people or PRs in `name` or `symptom_pattern`.
`steps` must only use tool names from the list you are given, in a sensible order, and should
be the shortest sequence that would have found the root cause."""


async def save_playbook(
    graph: GraphLike, llm: LLM, investigation_id: str, settings: Settings | None = None
) -> str | None:
    """Summarise a confirmed investigation into a Playbook node. Returns its id (or None).

    Only the symptom, the tool names used and the root cause's kind are shown to the model, not
    the tool outputs: a playbook is shared memory, so it must not carry restricted content.
    """
    settings = settings or get_settings()
    rows = await asyncio.to_thread(
        _read, graph, "memory_read_investigation", investigation_id=investigation_id
    )
    if not rows:
        return None
    inv = rows[0]
    tools_used = [t for t in (inv.get("tools") or []) if t]
    root_kind = (inv.get("root_cause") or "unknown").split(":")[0]  # "pr:482" -> "pr"
    prompt = (
        f"Symptom: {inv.get('symptom')}\n"
        f"Tools called, in order: {tools_used}\n"
        f"Root cause was a node of kind: {root_kind}\n"
        "Write the playbook."
    )
    resp = await llm.generate(
        settings.model_flash, PLAYBOOK_PROMPT, [user_text(prompt)], response_schema=PlaybookDraft
    )
    draft: PlaybookDraft | None = resp.parsed
    if draft is None:
        return None
    steps = [s for s in draft.steps if s in tools_used] or tools_used  # never invent tools
    [vec] = await llm.embed([draft.symptom_pattern], "document")
    playbook_id = f"playbook:{investigation_id.split(':')[-1]}"
    await asyncio.to_thread(
        _write,
        graph,
        "memory_save_playbook",
        investigation_id=investigation_id,
        id=playbook_id,
        name=draft.name,
        symptom_pattern=draft.symptom_pattern,
        steps=json.dumps(steps),
        embedding=vec,
        ts=_now(),
    )
    return playbook_id


def find_playbooks(graph: GraphLike, symptom_vec: list[float], k: int = 3) -> list[dict[str, Any]]:
    """Closest playbooks by meaning, ties broken by success_count. `steps` comes back as a list."""
    rows = _read(graph, "memory_find_playbooks", vec=symptom_vec, k=k)
    return [{**row, "steps": playbook_steps(row.get("steps"))} for row in rows]


def playbook_steps(raw: Any) -> list[str]:
    """Playbook.steps is stored as a JSON string; accept a native list too."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return [str(s) for s in raw] if isinstance(raw, list) else []


def mark_playbook_used(graph: GraphLike, investigation_id: str, playbook_id: str) -> None:
    _write(
        graph,
        "memory_mark_playbook_used",
        investigation_id=investigation_id,
        playbook_id=playbook_id,
    )


async def apply_feedback(
    graph: GraphLike,
    llm: LLM,
    investigation_id: str,
    confirmed: bool,
    settings: Settings | None = None,
) -> str | None:
    """✅/❌ from a human on the root cause.

    - The playbooks this investigation used get success_count +1 (✅) or -1 (❌).
    - A ✅ on an investigation that used no playbook teaches a new one.
    Returns the id of the playbook that was saved or adjusted, if any.
    """
    rows = await asyncio.to_thread(
        _write,
        graph,
        "memory_feedback",
        investigation_id=investigation_id,
        feedback="confirmed" if confirmed else "rejected",
        ts=_now(),
    )
    used = rows[0].get("used", []) if rows else []
    learned = rows[0].get("learned", []) if rows else []
    for playbook_id in used:
        await asyncio.to_thread(
            _write, graph, "memory_adjust_playbook", id=playbook_id, delta=1 if confirmed else -1
        )
    if used:
        return used[0]
    if confirmed and not learned:
        return await save_playbook(graph, llm, investigation_id, settings)
    return learned[0] if learned else None


# ------------------------------------------------------------------ semantic: expertise


def update_expertise(
    graph: GraphLike, person_id: str, service_id: str, score: float, now: int | None = None
) -> bool:
    """Record a new expertise score without overwriting history.

    The current EXPERT_IN edge gets `valid_to = now`, and a new edge starts at `now`.
    Returns False (and writes nothing) when the score has not changed.
    """
    now = now or _now()
    current = _read(graph, "memory_current_expertise", person_id=person_id, service_id=service_id)
    if current and current[0].get("score") == score:
        return False
    params = dict(person_id=person_id, service_id=service_id, now=now)
    _write(graph, "memory_expertise_close", **params)
    _write(graph, "memory_expertise_open", score=score, **params)
    return True


# ------------------------------------------------------------------ Ask trace


def record_query_trace(
    graph: GraphLike,
    *,
    question: str,
    viewer_id: str,
    mode: str,
    retrieved_ids: list[str],
    filtered_count: int,
    reranked_ids: list[str],
    cited_ids: list[str],
    refused: bool,
    ms: float,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> str:
    """Save the audit trail of one Ask question. Returns the Query node id."""
    trace_id = f"query:{uuid.uuid4().hex[:12]}"
    _write(
        graph,
        "memory_query_trace",
        id=trace_id,
        question=question,
        viewer_id=viewer_id,
        mode=mode,
        retrieved_ids=retrieved_ids,
        filtered_count=filtered_count,
        reranked_ids=reranked_ids,
        cited_ids=cited_ids,
        refused=refused,
        ms=round(ms, 1),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=round(cost_usd, 6),
        ts=_now(),
    )
    return trace_id
