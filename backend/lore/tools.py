"""Agent tools: small read-only Cypher queries wrapped as Python functions (plan section 8).

Rules every tool follows:
1. Runs through `GraphLike.ro()` (GRAPH.RO_QUERY), so it can never write.
2. Gets `viewer` + `open_levels` from `ToolContext`, added by the server. The model never sees them.
3. Has a required `reason` argument the model must fill (shown in the trail).
4. Returns a `ToolResult` with data + cypher + ms + node_ids (permitted ids only) + edges.

Model-visible arguments are declared as a Pydantic model per tool. `lore.llm` turns those models
into Gemini function declarations. `viewer` must NEVER appear in an args model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from lore.db import GraphLike, QueryOutcome, load_query
from lore.models import GraphMode, ToolResult, Viewer
from lore.permissions import permission_params


@dataclass
class ToolContext:
    viewer: Viewer
    graph: GraphLike
    mode: GraphMode = "graph"
    investigation_id: str | None = None
    # Every node id any tool returned during this run. The citation validator checks against it.
    seen_ids: set[str] = field(default_factory=set)
    # Investigation-time "now" (alert time), so "recent" means recent relative to the story.
    now_ts: int | None = None


class ToolArgs(BaseModel):
    reason: str = Field(description="One sentence: why you are calling this tool right now.")


NO_REASON = "(the model gave no reason for this call)"


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[ToolArgs]
    fn: Callable[[ToolContext, Any], ToolResult]
    modes: tuple[GraphMode, ...] = ("graph",)  # which modes may use it ("vector" = Graph OFF)


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, args_model: type[ToolArgs], modes=("graph",)):
    """Decorator that registers a tool function `fn(ctx, args) -> ToolResult`."""

    def wrap(fn):
        REGISTRY[name] = ToolSpec(name, description, args_model, fn, tuple(modes))
        return fn

    return wrap


def run_query(ctx: ToolContext, query_name: str, params: dict[str, Any]) -> QueryOutcome:
    """Load a .cypher file and run it read-only with the permission params merged in.

    Permission params are merged LAST so nothing the model passes can override them.
    """
    cypher = load_query(query_name)
    merged = {**params, **permission_params(ctx.viewer)}
    return ctx.graph.ro(cypher, merged)


def call_tool(ctx: ToolContext, name: str, raw_args: dict[str, Any]) -> ToolResult:
    """Validate model-supplied args, run the tool, record seen ids. Never raises: errors go in
    ToolResult.error so the agent can continue with other evidence (plan section 11)."""
    spec = REGISTRY.get(name)
    if spec is None:
        return ToolResult(tool=name, reason=str(raw_args.get("reason", "")), error="unknown tool")
    if ctx.mode not in spec.modes:
        return ToolResult(tool=name, reason="", error=f"tool not available in {ctx.mode} mode")
    raw_args = {k: v for k, v in raw_args.items() if k not in ("viewer", "open_levels")}
    if not str(raw_args.get("reason") or "").strip():
        # The model is told `reason` is required, but small models sometimes drop it. Run the
        # tool anyway instead of failing the step (FIX_LOG F-17); the trail shows NO_REASON.
        # (No log line: tools also run inside the MCP server, whose stdout is the protocol.)
        raw_args["reason"] = NO_REASON
    try:
        args = spec.args_model.model_validate(raw_args)
    except Exception as exc:  # pydantic.ValidationError
        reason = str(raw_args.get("reason", ""))
        return ToolResult(tool=name, reason=reason, error=f"bad args: {exc}")
    try:
        result = spec.fn(ctx, args)
    except Exception as exc:
        return ToolResult(tool=name, reason=args.reason, error=f"{type(exc).__name__}: {exc}")
    ctx.seen_ids.update(result.node_ids)
    return result


def tools_for(names: list[str], mode: GraphMode) -> list[ToolSpec]:
    """The subset of tools an agent may use in this mode."""
    return [REGISTRY[n] for n in names if n in REGISTRY and mode in REGISTRY[n].modes]


# ---------------------------------------------------------------------------------------------
# Tool implementations. Each one runs a file in lore/queries/. See docs/PROJECT_CONTEXT.md for
# which agent uses which tool.
# ---------------------------------------------------------------------------------------------

import asyncio  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from typing import Literal  # noqa: E402

from lore.models import EdgeRef  # noqa: E402

# ------------------------------------------------------------------ small helpers


def _unique(items) -> list:
    """Drop duplicates and empty values but keep the order."""
    return list(dict.fromkeys(i for i in items if i))


def _strip_comments(cypher: str) -> str:
    """The trail shows the query without its explanatory // header (the .cypher file keeps it)."""
    lines = [ln for ln in cypher.splitlines() if not ln.lstrip().startswith("//")]
    return "\n".join(lines).strip()


def _result(
    tool_name: str,
    args: ToolArgs,
    outcomes: QueryOutcome | list[QueryOutcome],
    data: list[dict],
    node_ids=(),
    edges=(),
    **extra,
) -> ToolResult:
    """Build the ToolResult: data + the Cypher that ran + timing + the graph piece touched."""
    outs = outcomes if isinstance(outcomes, list) else [outcomes]
    unique_edges = list({(e.source, e.target, e.type): e for e in edges}.values())
    return ToolResult(
        tool=tool_name,
        reason=args.reason,
        data=data,
        cypher="\n\n".join(_unique(_strip_comments(o.cypher) for o in outs)),
        ms=round(sum(o.ms for o in outs), 2),
        node_ids=_unique(node_ids),
        edges=unique_edges,
        **extra,
    )


def service_id(text: str) -> str:
    """'pricing' or 'Pricing' -> 'svc:pricing'. Ids pass through unchanged."""
    text = text.strip()
    return text if text.startswith("svc:") else "svc:" + text.lower().replace(" ", "-")


def pr_id(text: str) -> str:
    """'482', '#482', 'PR-482' -> 'pr:482'."""
    digits = re.sub(r"\D", "", str(text))
    return f"pr:{digits}" if digits else str(text)


def alert_id(text: str) -> str:
    text = text.strip()
    return text if text.startswith("alert:") else f"alert:{text}"


_TICKET_PREFIXES = "CHK|PRC|DSP|PAY|DAT|PLT"
_ID_PATTERNS = [  # (regex, id builder): turn how people type a name into how the graph stores it
    (re.compile(r"adr[-\s:#]*0*(\d+)$", re.I), lambda m: f"adr:{int(m[1]):03d}"),
    (re.compile(r"(?:pr[-\s:#]*|#)(\d+)$", re.I), lambda m: f"pr:{int(m[1])}"),
    (re.compile(r"inc[-\s:]*0*(\d+)$", re.I), lambda m: f"inc:INC-{int(m[1]):04d}"),
    (re.compile(rf"({_TICKET_PREFIXES})-(\d+)$", re.I), lambda m: f"ticket:{m[1].upper()}-{m[2]}"),
    (re.compile(r"(?:alert[-\s:]*)?(A-\d+)$", re.I), lambda m: f"alert:{m[1].upper()}"),
    (re.compile(r"deploy[-\s:#]*(\d+)$", re.I), lambda m: f"deploy:{int(m[1])}"),
]


def normalise_id(text: str) -> str:
    """Best guess for the graph id of a name: 'ADR-011' -> 'adr:011', 'pricing' -> 'svc:pricing'."""
    text = text.strip()
    for pattern, build in _ID_PATTERNS:
        m = pattern.match(text)
        if m:
            return build(m)
    if re.match(r"^[a-z]+:\S+$", text):  # already an id
        return text
    return service_id(text)


def guess_ids(text: str) -> list[str]:
    """Ids a name might stand for. find_entity matches any of them exactly."""
    return _unique([normalise_id(text), text.strip(), text.strip().lower()])


# ------------------------------------------------------------------ embeddings for tools

_embedder = None  # tests (or an offline demo) can plug in a function: text -> vector


def set_embedder(fn) -> None:
    """Use `fn(text) -> list[float]` instead of Gemini for tool-side embeddings."""
    global _embedder
    _embedder = fn


def embed_query(text: str) -> list[float]:
    """Embed a search text. Tools are plain sync functions but the LLM client is async, so run
    its coroutine on a private event loop (in a helper thread if a loop is already running)."""
    if _embedder is not None:
        return _embedder(text)
    from lore.config import get_settings  # lazy: lore.llm imports this module
    from lore.llm import fake_embedding, get_llm

    settings = get_settings()
    if settings.fake_embeddings:  # offline graph: no key needed
        return fake_embedding(text, settings.embed_dim)
    coro = get_llm(settings).embed([text], "query")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)[0]
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()[0]


# ------------------------------------------------------------------ 1. find_entity


class FindEntityArgs(ToolArgs):
    name: str = Field(
        description="A name or id to look up: a service ('pricing'), a person, a team, "
        "'ADR-011', 'PR 482', 'INC-0307', 'PRC-311'."
    )


@tool(
    "find_entity",
    "Look up a service, person, team, PR, ticket, ADR or incident by name or id. Returns its "
    "exact graph id (use that id in other tools), its type, and for a service its owning team.",
    FindEntityArgs,
    modes=("graph", "vector"),
)
def find_entity(ctx: ToolContext, args: FindEntityArgs) -> ToolResult:
    out = run_query(ctx, "find_entity", {"text": args.name, "ids": guess_ids(args.name)})
    rows = out.dicts()
    edges = [
        EdgeRef(source=r["owner_team"], target=r["id"], type="OWNS")
        for r in rows
        if r["owner_team"]
    ]
    ids = [r["id"] for r in rows] + [r["owner_team"] for r in rows]
    return _result("find_entity", args, out, rows, ids, edges)


# ------------------------------------------------------------------ 2. blast_radius


class BlastRadiusArgs(ToolArgs):
    service: str = Field(description="The failing service, e.g. 'checkout' or 'svc:checkout'.")


@tool(
    "blast_radius",
    "List every service that depends on the given service, directly or up to 4 hops away, with "
    "its tier (1 = most critical) and hop distance. The service itself is hops 0. Use it to see "
    "how far an outage spreads.",
    BlastRadiusArgs,
)
def blast_radius(ctx: ToolContext, args: BlastRadiusArgs) -> ToolResult:
    out = run_query(ctx, "blast_radius", {"service": service_id(args.service)})
    rows = out.dicts()
    edges = []
    for r in rows:  # via = [failing service, ..., this service]; each next one DEPENDS_ON the last
        via = r["via"]
        edges += [
            EdgeRef(source=via[i + 1], target=via[i], type="DEPENDS_ON")
            for i in range(len(via) - 1)
        ]
    return _result("blast_radius", args, out, rows, [r["id"] for r in rows], edges)


# ------------------------------------------------------------------ 3. service_criticality


class CriticalityArgs(ToolArgs):
    top: int = Field(default=5, ge=1, le=15, description="How many services to return.")


@tool(
    "service_criticality",
    "Rank services by how much the rest of the company depends on them (PageRank over DEPENDS_ON). "
    "Highest score = most critical.",
    CriticalityArgs,
)
def service_criticality(ctx: ToolContext, args: CriticalityArgs) -> ToolResult:
    out = run_query(ctx, "pagerank_services", {"limit": args.top})
    rows = out.dicts()
    return _result("service_criticality", args, out, rows, [r["id"] for r in rows])


# ------------------------------------------------------------------ 4. similar_incidents


class SimilarIncidentsArgs(ToolArgs):
    symptom: str = Field(
        description="What is going wrong, in plain words, e.g. 'checkout p99 latency'."
    )


@tool(
    "similar_incidents",
    "Find past incidents whose description is closest in meaning to the symptom. Returns the "
    "incident, its severity, the services it affected, who resolved it and which PR caused it. "
    "Only incidents you are allowed to see are returned.",
    SimilarIncidentsArgs,
    modes=("graph", "vector"),
)
def similar_incidents(ctx: ToolContext, args: SimilarIncidentsArgs) -> ToolResult:
    from lore.retrieval import FETCH_K, distance_to_similarity

    qvec = embed_query(args.symptom)
    out = run_query(ctx, "similar_incidents", {"qvec": qvec, "fetch_k": FETCH_K, "k": 5})
    rows = out.dicts()
    ids, edges = [], []
    for r in rows:
        r["similarity"] = round(distance_to_similarity(r.pop("score")), 3)
        ids += [r["id"], r["resolved_by"], r["caused_by"], *r["services"]]
        edges += [EdgeRef(source=r["id"], target=s, type="AFFECTED") for s in r["services"]]
        if r["resolved_by"]:
            edges.append(EdgeRef(source=r["id"], target=r["resolved_by"], type="RESOLVED_BY"))
        if r["caused_by"]:
            edges.append(EdgeRef(source=r["id"], target=r["caused_by"], type="CAUSED_BY"))
    return _result("similar_incidents", args, out, rows, ids, edges)


# ------------------------------------------------------------------ 5. get_playbook

PLAYBOOK_MAX_DISTANCE = 0.4  # how close (cosine distance) a symptom must be to reuse a playbook


class GetPlaybookArgs(ToolArgs):
    symptom: str = Field(description="The current symptom, e.g. 'dispatch assignment latency'.")


@tool(
    "get_playbook",
    "Look up a learned playbook for this kind of symptom: an ordered list of tools that found the "
    "root cause last time. Returns an empty list if Lore has not learned one yet.",
    GetPlaybookArgs,
)
def get_playbook(ctx: ToolContext, args: GetPlaybookArgs) -> ToolResult:
    params = {"qvec": embed_query(args.symptom), "max_distance": PLAYBOOK_MAX_DISTANCE, "k": 3}
    out = run_query(ctx, "get_playbook", params)
    rows = out.dicts()
    for r in rows:  # steps is stored as a JSON string
        try:
            r["steps"] = json.loads(r["steps"]) if isinstance(r["steps"], str) else r["steps"]
        except json.JSONDecodeError:
            r["steps"] = []
    return _result("get_playbook", args, out, rows, [r["id"] for r in rows])


# ------------------------------------------------------------------ 6. search_discussions


class SearchDiscussionsArgs(ToolArgs):
    query: str = Field(description="What to look for, e.g. 'why is the pricing cache TTL 300s'.")
    service: str = Field(
        default="",
        description="Optional: a service to focus on. Also searches sources about nearby services.",
    )


@tool(
    "search_discussions",
    "Search Slack threads, tickets, ADRs, docs and incidents for the query, by meaning and (in "
    "graph mode) by exact words and nearby services. Returns the best sources with a score "
    "breakdown. Also reports how many matching sources you are NOT allowed to see.",
    SearchDiscussionsArgs,
    modes=("graph", "vector"),
)
def search_discussions(ctx: ToolContext, args: SearchDiscussionsArgs) -> ToolResult:
    from lore import rerank, retrieval

    outcomes: list[QueryOutcome] = []
    qvec = embed_query(args.query)
    found = retrieval.vector_search(ctx, qvec, 10, outcomes=outcomes)
    if ctx.mode == "graph":  # graph OFF = vector search only (the eval baseline)
        found += retrieval.fulltext_search(ctx, args.query, 10, outcomes=outcomes)
        if args.service:
            found += retrieval.graph_scoped_search(
                ctx, service_id(args.service), qvec, 10, outcomes=outcomes
            )
    ranked = rerank.rerank(found, ctx.now_ts or int(time.time()))[:8]
    hidden, hint = retrieval.restricted_match_count(ctx, qvec, outcomes=outcomes)
    rows = [
        {
            "id": c.id,
            "title": c.title,
            "source": c.source,
            "access_level": c.access_level,
            "updated_at": c.updated_at,
            "text": c.text[:600],
            "score": round(c.score, 3),
            "why": rerank.explain(c),
        }
        for c in ranked
    ]
    return _result(
        "search_discussions",
        args,
        outcomes,
        rows,
        [c.id for c in ranked],
        restricted_matches=hidden,
        restricted_owner_hint=hint,
    )


# ------------------------------------------------------------------ 7. recent_changes


class RecentChangesArgs(ToolArgs):
    service: str = Field(description="The failing service. Its dependencies (3 hops) are included.")
    hours: int = Field(
        default=24, ge=1, le=168, description="Look back this many hours from the alert."
    )


@tool(
    "recent_changes",
    "List deploys, the PRs inside them, their authors and the code modules they changed, for the "
    "service and everything it depends on (up to 3 hops), in the last N hours before the alert. "
    "These are the suspects; compare the modules changed to tell a real cause from a red herring.",
    RecentChangesArgs,
)
def recent_changes(ctx: ToolContext, args: RecentChangesArgs) -> ToolResult:
    now = ctx.now_ts or int(time.time())  # during an investigation: the alert time
    params = {"service": service_id(args.service), "since": now - args.hours * 3600, "until": now}
    out = run_query(ctx, "recent_changes", params)
    rows = out.dicts()
    ids, edges = [], []
    for r in rows:
        ids += [r["service_id"], r["deploy_id"], r["pr_id"], r["author_id"], *r["modules"]]
        edges += [
            EdgeRef(source=r["deploy_id"], target=r["service_id"], type="DEPLOYED_TO"),
            EdgeRef(source=r["deploy_id"], target=r["pr_id"], type="INCLUDES"),
        ]
        if r["author_id"]:
            edges.append(EdgeRef(source=r["author_id"], target=r["pr_id"], type="AUTHORED"))
        edges += [EdgeRef(source=r["pr_id"], target=m, type="MODIFIES") for m in r["modules"]]
    return _result("recent_changes", args, out, rows, ids, edges)


# ------------------------------------------------------------------ 8. evidence_path


class EvidencePathArgs(ToolArgs):
    alert_id: str = Field(description="The alert, e.g. 'A-3001'.")
    pr_number: str = Field(description="The suspect PR number, e.g. '482'.")


@tool(
    "evidence_path",
    "Find the shortest chain in the graph from the alert to a suspect PR (alert, service, "
    "dependencies, deploy, PR). Returns the node ids in order and the edges between them. An "
    "empty result means no such chain exists, so the PR is probably not the cause.",
    EvidencePathArgs,
)
def evidence_path(ctx: ToolContext, args: EvidencePathArgs) -> ToolResult:
    params = {"alert": alert_id(args.alert_id), "pr": pr_id(args.pr_number)}
    try:
        out = run_query(ctx, "evidence_path", params)
    except Exception:  # the algorithm call failed: retry with plain Cypher shortestPath
        out = run_query(ctx, "evidence_path_fallback", params)
    rows = out.dicts()
    if not rows:
        return _result("evidence_path", args, out, [])
    r = rows[0]
    edges = [
        EdgeRef(source=s, target=t, type=ty)
        for s, t, ty in zip(r["rel_sources"], r["rel_targets"], r["rel_types"], strict=True)
    ]
    data = [{"path": r["node_ids"], "edges": [e.model_dump() for e in edges], "length": len(edges)}]
    return _result("evidence_path", args, out, data, r["node_ids"], edges)


# ------------------------------------------------------------------ 9. trace_decision


class TraceDecisionArgs(ToolArgs):
    entity: str = Field(
        description="A decision ('ADR-011'), a service ('pricing') or a PR ('PR 482')."
    )


@tool(
    "trace_decision",
    "Trace the decision trail around an ADR, a service or a PR: the decision, the Slack threads "
    "where it was discussed, documents it replaced, and past incidents on the same service. "
    "Also reports how many related discussion threads you are NOT allowed to see.",
    TraceDecisionArgs,
)
def trace_decision(ctx: ToolContext, args: TraceDecisionArgs) -> ToolResult:
    entity = normalise_id(args.entity)
    out = run_query(
        ctx, "trace_decision", {"entity": entity, "entity_short": entity.split(":", 1)[-1]}
    )
    rows = out.dicts()
    ids, edges, hidden, hint = [], [], 0, None
    for r in rows:
        d = r["decision_id"]
        # OPTIONAL MATCH with no visible thread still collects one {id: null} map: drop it.
        r["thread_notes"] = [n for n in r.get("thread_notes") or [] if n.get("id")]
        ids += [d, *r["threads"], *r["supersedes"], *r["superseded_by"]]
        edges += [EdgeRef(source=d, target=t, type="DISCUSSED_IN") for t in r["threads"]]
        edges += [EdgeRef(source=d, target=o, type="SUPERSEDES") for o in r["supersedes"]]
        edges += [EdgeRef(source=n, target=d, type="SUPERSEDES") for n in r["superseded_by"]]
        for pair in r["incidents"]:
            ids += [pair["incident"], pair["postmortem"]]
            if pair["incident"] and pair["postmortem"]:
                edges.append(
                    EdgeRef(source=pair["incident"], target=pair["postmortem"], type="RECORDED_IN")
                )
        hidden += r["hidden_threads"] or 0
        hint = hint or (f"ask the {r['hidden_team'].title()} team" if r["hidden_team"] else None)
    return _result(
        "trace_decision",
        args,
        out,
        rows,
        ids,
        edges,
        restricted_matches=hidden,
        restricted_owner_hint=hint if hidden else None,
    )


# ------------------------------------------------------------------ 10. who_knows


class WhoKnowsArgs(ToolArgs):
    service: str = Field(description="The service, e.g. 'pricing' or 'svc:pricing'.")


def classify_experts(rows: list[dict], max_consult: int = 3) -> list[dict]:
    """Turn who_knows rows into 'page' (the owner) and 'consult' (the experts).

    - page: the lead of the team that currently owns the service (else its top-scoring member).
    - consult: the next highest-scoring people with a score above 0, wherever they work now.
    Someone who moved away (Marco) is not on the owner team, so they can only be a consult.
    """
    people: dict[str, dict] = {}
    for r in rows:  # the UNION can return the same person twice
        p = people.setdefault(r["id"], {**r, "on_owner_team": False, "is_lead": False})
        p["score"] = max(p["score"], r["score"])
        p["on_owner_team"] = p["on_owner_team"] or bool(r["on_owner_team"])
        p["is_lead"] = p["is_lead"] or bool(r["is_lead"])
    ordered = sorted(people.values(), key=lambda p: (-p["score"], p["id"]))
    owners = [p for p in ordered if p["on_owner_team"]]
    page = next((p for p in owners if p["is_lead"]), owners[0] if owners else None)
    consult = [p for p in ordered if p is not page and p["score"] > 0][:max_consult]
    authors = sum(1 for p in ordered if (p.get("authored") or 0) > 0)

    result = []
    for role, group in (("page", [page] if page else []), ("consult", consult)):
        for p in group:
            if role == "page":
                why = f"leads {p['current_team']}, which owns the service"
            else:
                why = f"{p['code_score']} code points + {p['incident_score']} incident points"
                why += f"; now in {p['current_team']}" if p["current_team"] else ""
            result.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "role": role,
                    "score": p["score"],
                    "code_score": p["code_score"],
                    "incident_score": p["incident_score"],
                    "current_team": p["current_team"],
                    "owner_team": p["owner_team"],
                    "reason": why,
                    "authors_on_service": authors,
                    "bus_factor_1": authors == 1,
                }
            )
    return result


@tool(
    "who_knows",
    "Find who to contact about a service. 'page' = the owner on the org chart (the team lead of "
    "the owning team); 'consult' = people who really know the code, scored by PRs written (3 "
    "points), PRs reviewed (1) and past incidents fixed (5). Also flags a bus factor of 1 when "
    "only one person has ever written code in the service. Never page a 'consult'.",
    WhoKnowsArgs,
)
def who_knows(ctx: ToolContext, args: WhoKnowsArgs) -> ToolResult:
    svc = service_id(args.service)
    out = run_query(ctx, "who_knows", {"service": svc})
    people = classify_experts(out.dicts())
    ids, edges = [svc], []
    for p in people:
        ids += [p["id"], p["current_team"], p["owner_team"]]
        if p["current_team"]:
            edges.append(EdgeRef(source=p["id"], target=p["current_team"], type="MEMBER_OF"))
        if p["owner_team"]:
            edges.append(EdgeRef(source=p["owner_team"], target=svc, type="OWNS"))
    return _result("who_knows", args, out, people, ids, edges)


# ------------------------------------------------------------------ 11. propose_action


class ProposeActionArgs(ToolArgs):
    kind: Literal["slack_post", "github_issue", "rollback"] = Field(
        description="slack_post (a message), github_issue (a ticket) or rollback (simulated)."
    )
    target: str = Field(
        description="Where it goes: a Slack channel like '#incidents', or 'owner/repo'."
    )
    text: str = Field(description="The message or issue body. Plain text, factual, no secrets.")
    cited_ids: list[str] = Field(
        description="Ids of the sources this text relies on (from earlier tools)."
    )
    title: str = Field(default="", description="Title, for a GitHub issue.")


@tool(
    "propose_action",
    "Draft an outward action for a human to review: a Slack post, a GitHub issue or a rollback. "
    "Nothing is sent until a person edits and approves it. Only cite sources that other tools "
    "returned; a post is blocked if someone in the channel may not see a cited source.",
    ProposeActionArgs,
    modes=("graph", "vector"),
)
def propose_action(ctx: ToolContext, args: ProposeActionArgs) -> ToolResult:
    from lore import actions  # lazy: written by the API work package
    from lore.config import get_settings

    target, title = args.target, args.title or None
    if args.kind == "github_issue":
        # Issues always go to the configured demo repo; show that, not the model's guess, to
        # the person approving (FIX_LOG F-04). A missing title gets a plain default.
        target = get_settings().github_repo or target
        title = title or f"Incident follow-up: {args.text.split('.')[0][:80]}"
    action = actions.propose(
        investigation_id=ctx.investigation_id,
        kind=args.kind,
        target=target,
        text=args.text,
        cited_ids=args.cited_ids,
        title=title,
    )
    unseen = [c for c in args.cited_ids if c not in ctx.seen_ids]
    data = [{**action.model_dump(), "unverified_citations": unseen}]
    # Highlight what the draft cites (graph nodes), not the action id, which is not in the graph
    # and made the UI zoom onto an empty spot (FIX_LOG F-12).
    cited = [c for c in args.cited_ids if c in ctx.seen_ids]
    return ToolResult(tool="propose_action", reason=args.reason, data=data, node_ids=cited)
