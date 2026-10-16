"""Shared data shapes. Every module talks to every other module through these.

Changing a field here is a contract change: update docs/PROJECT_CONTEXT.md and the
frontend types in frontend/src/api/types.ts in the same commit.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- identity


class AccessLevel(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class Viewer(BaseModel):
    """The logged-in person. Built by the server from the session, NEVER by the model."""

    id: str  # "person:arjun"
    name: str
    employment: Literal["employee", "contractor"] = "employee"

    @property
    def open_levels(self) -> list[str]:
        """Access levels open to this viewer without any graph path (plan section 9)."""
        if self.employment == "contractor":
            return [AccessLevel.PUBLIC.value]
        return [AccessLevel.PUBLIC.value, AccessLevel.INTERNAL.value]


class Persona(BaseModel):
    id: str  # "arjun"
    person_id: str  # "person:arjun"
    name: str
    role: str
    can_see: str
    employment: Literal["employee", "contractor"] = "employee"

    def viewer(self) -> Viewer:
        return Viewer(id=self.person_id, name=self.name, employment=self.employment)


# ---------------------------------------------------------------- tools

GraphMode = Literal["graph", "vector"]  # "vector" = the Graph OFF baseline


class EdgeRef(BaseModel):
    source: str  # node id property, e.g. "svc:checkout"
    target: str
    type: str  # "DEPENDS_ON"


class ToolResult(BaseModel):
    """What every tool returns. Design rule 1: tools return the piece of graph they touched."""

    tool: str
    reason: str  # why the model called it (shown in the trail)
    data: list[dict[str, Any]] = Field(default_factory=list)
    cypher: str = ""
    ms: float = 0.0
    node_ids: list[str] = Field(default_factory=list)  # permitted ids only
    edges: list[EdgeRef] = Field(default_factory=list)
    restricted_matches: int = 0  # matching sources the viewer may not see (count only)
    restricted_owner_hint: str | None = None  # "ask the Pricing team (Rahul)"
    error: str | None = None


# ---------------------------------------------------------------- streaming events

EventType = Literal[
    "investigation_started",
    "agent_started",
    "tool_call",
    "tool_result",
    "finding",
    "agent_finished",
    "report",
    "action_proposed",
    "policy_blocked",
    "error",
    "done",
]


class StepEvent(BaseModel):
    """One SSE message. The frontend renders the trail and graph highlights from these."""

    type: EventType
    investigation_id: str
    seq: int
    ts: float
    agent: str | None = None  # "triage" | "historian" | "investigator" | "responder"
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------- reports and answers


class Claim(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)  # node ids returned by tools this run


class PeopleToContact(BaseModel):
    page: str | None = None  # owner on call, e.g. "person:rahul"
    consult: list[str] = Field(default_factory=list)  # experts, e.g. ["person:marco"]
    notify: list[str] = Field(default_factory=list)  # authors, e.g. ["person:priya"]


class Report(BaseModel):
    """The Investigator/Responder's final structured output (plan section 8)."""

    summary: str
    root_cause: str | None = None  # node id, e.g. "pr:482"
    rejected_suspects: list[Claim] = Field(default_factory=list)  # red herrings + why
    severity: Literal["P1", "P2", "P3"] | None = None  # set by policy.py, never by the model
    claims: list[Claim] = Field(default_factory=list)
    evidence_path: list[str] = Field(default_factory=list)
    people: PeopleToContact = Field(default_factory=PeopleToContact)
    confidence: float = 0.0
    restricted_matches: int = 0
    restricted_owner_hint: str | None = None
    dropped_claims: list[Claim] = Field(default_factory=list)  # failed citation validation


class SourceRef(BaseModel):
    id: str
    source: str  # "slack" | "github" | "jira" | "adr" | "wiki" | "runbook" | "incident" ...
    title: str | None = None
    updated_at: int | None = None
    access_level: AccessLevel | None = None
    conflict: bool = False  # tagged when it disagrees with a higher-ranked source


class AskAnswer(BaseModel):
    question: str
    viewer_id: str
    mode: GraphMode = "graph"
    claims: list[Claim] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    refused: bool = False
    restricted_matches: int = 0
    restricted_owner_hint: str | None = None
    query_trace_id: str | None = None
    ms: float = 0.0


# ---------------------------------------------------------------- actions (human in the loop)

ActionKind = Literal["slack_post", "github_issue", "rollback"]
ActionStatus = Literal["proposed", "approved", "rejected", "blocked", "sent", "failed"]


class Action(BaseModel):
    id: str  # "action:<uuid>"
    investigation_id: str
    kind: ActionKind
    target: str  # "#incidents" or "owner/repo"
    title: str | None = None
    text: str
    cited_ids: list[str] = Field(default_factory=list)
    status: ActionStatus = "proposed"
    blocked_reason: str | None = None
    result_url: str | None = None  # Slack permalink / GitHub issue URL once sent
    simulated: bool = False  # rollbacks are always simulated


# ---------------------------------------------------------------- graph view for the UI


class GraphNode(BaseModel):
    id: str
    label: str
    name: str
    access_level: AccessLevel | None = None
    props: dict[str, Any] = Field(default_factory=dict)


class GraphView(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    links: list[EdgeRef] = Field(default_factory=list)


class RunSummary(BaseModel):
    investigation_id: str
    steps: int = 0
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    total_ms: float = 0.0
    time_to_root_cause_ms: float | None = None
    replay: bool = False
