"""Agent loop and Supervisor with FakeLLM + fake tools (no FalkorDB, no Gemini)."""

from __future__ import annotations

import pytest
from pydantic import ConfigDict

from lore import tools
from lore.agents import supervisor
from lore.agents.base import AgentSpec, Blackboard, FindingsDraft, run_agent
from lore.config import Settings
from lore.llm import FakeLLM, LLMResponse
from lore.models import Action, StepEvent, ToolResult, Viewer
from lore.observability import RunMetrics
from lore.tools import ToolArgs, ToolContext, ToolSpec
from tests.fakes import outcome
from tests.test_memory import MemoryGraph

SECRET_VIEWER = Viewer(id="person:zz-viewer-7", name="Zed")


class AnyArgs(ToolArgs):
    model_config = ConfigDict(extra="allow")


# What each fake tool "returns": node ids (+ rows for the ones code reads).
FAKE_IDS = {
    "find_entity": ["svc:checkout"],
    "blast_radius": ["svc:checkout", "svc:api-gateway"],
    "service_criticality": ["svc:checkout"],
    "similar_incidents": ["inc:INC-0307"],
    "get_playbook": [],
    "search_discussions": ["adr:011"],
    "recent_changes": ["pr:482", "pr:479", "deploy:991", "deploy:990"],
    "evidence_path": [
        "alert:A-3001",
        "svc:checkout",
        "svc:promo-engine",
        "svc:pricing",
        "deploy:991",
        "pr:482",
    ],
    "trace_decision": ["adr:011"],
    "who_knows": ["person:rahul", "person:marco", "person:priya"],
}
BLAST_ROWS = [
    {"id": "svc:checkout", "tier": 1, "hops": 0},
    {"id": "svc:api-gateway", "tier": 1, "hops": 1},
]


@pytest.fixture
def fake_tools(monkeypatch):
    """Replace every agent tool with a fake that records the args it received."""
    received: list[tuple[str, dict]] = []
    rows = {"blast_radius": BLAST_ROWS, "get_playbook": []}

    def make(name):
        def fn(ctx, args):
            received.append((name, args.model_dump()))
            if name == "propose_action":
                action = Action(
                    id="action:1",
                    investigation_id=ctx.investigation_id or "",
                    kind="slack_post",
                    target="#incidents",
                    text="hi",
                )
                data = [{**action.model_dump(), "unverified_citations": []}]
                return ToolResult(tool=name, reason=args.reason, data=data, node_ids=[action.id])
            return ToolResult(
                tool=name,
                reason=args.reason,
                data=rows.get(name, [{"ok": 1}]),
                node_ids=FAKE_IDS[name],
                cypher=f"// {name}",
                ms=1.0,
            )

        return fn

    for name in [*FAKE_IDS, "propose_action"]:
        monkeypatch.setitem(
            tools.REGISTRY, name, ToolSpec(name, f"fake {name}", AnyArgs, make(name), ("graph",))
        )
    return {"received": received, "rows": rows}


class Recorder:
    def __init__(self):
        self.events: list[StepEvent] = []

    async def __call__(self, event: StepEvent) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]

    def of(self, type_: str) -> list[StepEvent]:
        return [e for e in self.events if e.type == type_]


def model_inputs(fake: FakeLLM) -> str:
    """Everything the model was ever shown, as one string."""
    out = []
    for call in fake.calls:
        out.append(call["system"])
        out += [c.model_dump_json() for c in call["contents"] if c is not None]
    return "\n".join(out)


def make_bb(graph, steps=4) -> Blackboard:
    return Blackboard("inv:t", graph, Settings(max_agent_steps=steps), RunMetrics("inv:t"))


def findings(text="Checkout is tier 1", cites=("svc:checkout",), confidence=0.9, **kw):
    return FakeLLM.structured(
        {"findings": [{"text": text, "citations": list(cites)}], "confidence": confidence, **kw}
    )


# ------------------------------------------------------------------ the agent loop


async def test_agent_loop_emits_events_in_order_and_never_shows_the_viewer(fake_tools):
    fake = FakeLLM(
        [
            FakeLLM.call(
                "blast_radius", reason="See the spread", service="checkout", viewer="person:dana"
            ),  # the model trying to pick a viewer is ignored
            FakeLLM.answer("Checkout and the gateway are affected."),
            findings(),
        ]
    )
    ctx = ToolContext(viewer=SECRET_VIEWER, graph=MemoryGraph(), investigation_id="inv:t")
    rec = Recorder()
    spec = AgentSpec("triage", "m", "You are Triage.", ["blast_radius"])

    out = await run_agent(spec, "What is broken?", ctx, fake, rec, make_bb(ctx.graph))

    assert rec.types() == ["agent_started", "tool_call", "tool_result", "finding", "agent_finished"]
    assert [e.seq for e in rec.events] == [1, 2, 3, 4, 5]
    call = rec.of("tool_call")[0].payload
    assert call == {
        "tool": "blast_radius",
        "reason": "See the spread",
        "args": {"service": "checkout"},
    }
    result = rec.of("tool_result")[0].payload
    assert result["node_ids"] == FAKE_IDS["blast_radius"] and result["row_count"] == 2
    assert set(result) >= {"tool", "reason", "cypher", "ms", "edges", "restricted_matches", "error"}
    # The tool never received a model-chosen viewer, and the model never saw the real one.
    assert "viewer" not in fake_tools["received"][0][1]
    assert "zz-viewer-7" not in model_inputs(fake)
    assert out.findings[0].citations == ["svc:checkout"] and out.confidence == 0.9
    assert out.tool_results[0].tool == "blast_radius"


async def test_uncited_claim_gets_one_retry_with_the_problems(fake_tools):
    fake = FakeLLM(
        [
            FakeLLM.call("blast_radius", reason="r", service="checkout"),
            FakeLLM.answer("done"),
            findings(text="Something with no source", cites=()),
            findings(),  # fixed on the retry
        ]
    )
    ctx = ToolContext(viewer=SECRET_VIEWER, graph=MemoryGraph())
    spec = AgentSpec("triage", "m", "sys", ["blast_radius"])
    out = await run_agent(spec, "goal", ctx, fake, Recorder(), make_bb(ctx.graph))

    retry_prompt = fake.calls[-1]["contents"][-1].parts[0].text
    assert "no citations" in retry_prompt
    assert fake.calls[-1]["response_schema"] is FindingsDraft
    assert [c.text for c in out.findings] == ["Checkout is tier 1"] and out.dropped == []


async def test_claims_still_invalid_after_retry_are_dropped(fake_tools):
    bad = findings(text="PR 999 did it", cites=("pr:999",), confidence=0.95)
    fake = FakeLLM(
        [FakeLLM.call("blast_radius", reason="r", service="x"), FakeLLM.answer("done"), bad, bad]
    )
    ctx = ToolContext(viewer=SECRET_VIEWER, graph=MemoryGraph())
    rec = Recorder()
    out = await run_agent(
        AgentSpec("triage", "m", "sys", ["blast_radius"]),
        "goal",
        ctx,
        fake,
        rec,
        make_bb(ctx.graph),
    )
    assert out.findings == [] and out.dropped[0].citations == ["pr:999"]
    assert out.confidence == 0.0  # no supported finding, no confidence
    assert rec.of("finding") == []


async def test_loop_stops_after_max_steps(fake_tools):
    def never_satisfied(model, system, contents, tools_, schema):
        """Always asks for another tool, except when asked for the final findings."""
        if schema is not None:
            return findings(cites=("svc:checkout",))
        return FakeLLM.call("blast_radius", reason="again", service="x")

    fake = FakeLLM(default=never_satisfied)
    ctx = ToolContext(viewer=SECRET_VIEWER, graph=MemoryGraph())
    rec = Recorder()
    await run_agent(
        AgentSpec("triage", "m", "sys", ["blast_radius"]),
        "g",
        ctx,
        fake,
        rec,
        make_bb(ctx.graph, steps=3),
    )
    assert len(rec.of("tool_call")) == 3


# ------------------------------------------------------------------ the supervisor

PLANS = {  # agent -> the tool calls its fake model makes, in order
    "triage": [
        ("find_entity", {"name": "checkout"}),
        ("blast_radius", {"service": "svc:checkout"}),
    ],
    "historian": [
        ("similar_incidents", {"symptom": "latency"}),
        ("get_playbook", {"symptom": "x"}),
    ],
    "investigator": [
        ("recent_changes", {"service": "svc:checkout"}),
        ("evidence_path", {"alert_id": "A-3001", "pr_number": "482"}),
    ],
    "responder": [
        ("who_knows", {"service": "svc:pricing"}),
        (
            "propose_action",
            {"kind": "slack_post", "target": "#incidents", "text": "t", "cited_ids": ["pr:482"]},
        ),
    ],
}
FINDING_FOR = {
    "triage": ("Checkout (tier 1) is affected.", ["svc:checkout"]),
    "historian": ("INC-0307 had the same pattern.", ["inc:INC-0307"]),
    "investigator": ("PR 482 lowered the pricing cache TTL.", ["pr:482", "deploy:991"]),
    "responder": ("Page Rahul, consult Marco.", ["person:rahul", "person:marco"]),
}


def agent_of(system: str) -> str:
    for name in ("Triage", "Historian", "Investigator", "Responder"):
        if f"You are {name}" in system or f"You are the {name}" in system:
            return name.lower()
    return "reporter"


class Brain:
    """A fake model that follows PLANS, then writes FINDING_FOR. The Investigator is unsure on
    its first pass (0.4) so the Supervisor must retry it."""

    def __init__(self, fail_agent: str | None = None):
        self.investigator_passes = 0
        self.fail_agent = fail_agent

    def __call__(self, model, system, contents, tools_, schema) -> LLMResponse:
        agent = agent_of(system)
        if agent == self.fail_agent:
            raise RuntimeError("quota exceeded")
        if schema is supervisor.ReportDraft:
            return FakeLLM.structured(
                {
                    "summary": "PR 482 caused it. Severity P3.",  # the model's opinion is ignored
                    "root_cause": "pr:482",
                    "rejected_suspects": [
                        {"text": "Rejected: PR 479 only changed copy.", "citations": ["pr:479"]}
                    ],
                    "claims": [
                        {"text": "PR 482 lowered the TTL.", "citations": ["pr:482"]},
                        {"text": "Invented fact.", "citations": ["pr:999"]},
                    ],
                    "people": {
                        "page": "person:rahul",
                        "consult": ["person:marco", "person:ghost"],
                        "notify": ["person:priya"],
                    },
                }
            )
        if schema is FindingsDraft:
            text, cites = FINDING_FOR[agent]
            confidence, root = 0.9, None
            if agent == "investigator":
                self.investigator_passes += 1
                confidence = 0.4 if self.investigator_passes == 1 else 0.9
                root = "pr:482"
            return findings(text=text, cites=cites, confidence=confidence, root_cause=root)
        done = sum(1 for c in contents if c.role == "user" and c.parts[0].function_response)
        plan = PLANS[agent]
        if done < len(plan):
            name, args = plan[done]
            return FakeLLM.call(name, reason=f"{agent} step {done}", **args)
        return FakeLLM.answer(f"{agent} done")


def alert_graph() -> MemoryGraph:
    return MemoryGraph(
        {
            "alert_context:": outcome(
                ["id", "symptom", "started_at", "service"],
                ["alert:A-3001", "checkout p99 latency > 3s", 1_791_000_000, "svc:checkout"],
            )
        }
    )


async def test_supervisor_runs_fixed_order_retries_investigator_and_sets_severity_in_code(
    fake_tools, monkeypatch
):
    severity_calls = []
    real = supervisor.policy.severity_for

    def spy(rows, *a, **kw):
        severity_calls.append(rows)
        return real(rows, *a, **kw)

    monkeypatch.setattr(supervisor.policy, "severity_for", spy)
    brain = Brain()
    fake = FakeLLM(default=brain)
    rec = Recorder()
    graph = alert_graph()

    report, summary = await supervisor.run_investigation(
        "alert:A-3001",
        SECRET_VIEWER,
        llm=fake,
        graph=graph,
        emit=rec,
        settings=Settings(max_agent_steps=5),
    )

    started = [e.payload["agent"] for e in rec.of("agent_started")]
    assert started == ["triage", "historian", "investigator", "investigator", "responder"]
    assert "one more hop" in rec.of("agent_started")[3].payload["goal"]

    # Severity: computed by policy from the blast radius rows, not the model's "P3".
    assert severity_calls == [BLAST_ROWS] and report.severity == "P1"

    # Report: invalid citations dropped, people filtered to ids tools returned.
    assert report.root_cause == "pr:482"
    assert [c.citations for c in report.claims] == [["pr:482"]]
    assert report.dropped_claims[0].citations == ["pr:999"]
    assert report.rejected_suspects[0].citations == ["pr:479"]
    assert report.people.page == "person:rahul" and report.people.consult == ["person:marco"]
    assert report.evidence_path == FAKE_IDS["evidence_path"]
    assert report.confidence == 0.9

    # Events: one stream, seq strictly increasing, starts and ends correctly.
    types = rec.types()
    assert types[0] == "investigation_started" and types[-1] == "done"
    assert types.index("report") < types.index("done")
    assert "action_proposed" in types
    seqs = [e.seq for e in rec.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert rec.of("done")[0].payload["investigation_id"] == summary.investigation_id

    # Summary: counted by code.
    assert summary.steps == len(rec.of("tool_result"))
    assert summary.model_calls == len(fake.calls)
    assert summary.time_to_root_cause_ms is not None

    # Memory: investigation opened, steps and findings written, closed.
    assert len(graph.written("memory_start_investigation")) == 1
    assert len(graph.written("memory_record_step")) == summary.steps
    assert graph.written("memory_finish_investigation")[0]["root_cause"] == "pr:482"

    # The viewer never reached the model or the tool_call events.
    assert "zz-viewer-7" not in model_inputs(fake)
    assert all("zz-viewer-7" not in str(e.payload) for e in rec.of("tool_call"))


async def test_supervisor_hands_playbook_steps_to_investigator(fake_tools):
    fake_tools["rows"]["get_playbook"] = [
        {"id": "playbook:abc", "steps": '["recent_changes", "evidence_path"]', "success_count": 2}
    ]
    rec = Recorder()
    graph = alert_graph()
    await supervisor.run_investigation(
        "alert:A-3001",
        SECRET_VIEWER,
        llm=FakeLLM(default=Brain()),
        graph=graph,
        emit=rec,
        settings=Settings(max_agent_steps=5),
    )
    goal = rec.of("agent_started")[2].payload["goal"]
    assert "playbook:abc" in goal and "recent_changes, evidence_path" in goal
    assert graph.written("memory_mark_playbook_used")[0]["playbook_id"] == "playbook:abc"


async def test_supervisor_survives_an_agent_failure(fake_tools):
    rec = Recorder()
    report, _ = await supervisor.run_investigation(
        "alert:A-3001",
        SECRET_VIEWER,
        llm=FakeLLM(default=Brain(fail_agent="historian")),
        graph=alert_graph(),
        emit=rec,
        settings=Settings(max_agent_steps=5),
    )
    errors = rec.of("error")
    assert errors and errors[0].agent == "historian" and errors[0].payload["recoverable"]
    assert [e.payload["agent"] for e in rec.of("agent_finished")][-1] == "responder"
    assert rec.types()[-1] == "done" and report.root_cause == "pr:482"


def test_graph_off_investigator_gets_text_search_and_an_honest_note():
    from lore.agents import investigator
    from lore.agents.base import VECTOR_MODE_NOTE, for_mode

    spec = investigator.spec(Settings())
    off = for_mode(spec, "vector")
    # every graph-mode Investigator tool is graph-only, so Graph OFF must offer something else
    assert tools.tools_for(spec.tool_names, "vector") == []
    assert [t.name for t in tools.tools_for(off.tool_names, "vector")] == [
        "search_discussions", "similar_incidents"]
    assert off.system_prompt.endswith(VECTOR_MODE_NOTE)
    assert for_mode(spec, "graph") is spec
