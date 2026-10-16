"""End-to-end Story A against a live FalkorDB, with a scripted model instead of Gemini.

The model's choices are scripted (which tools, which ids to cite), but everything else is real:
the Supervisor, the agent loop, the Cypher tools, the permission filter, memory writes and the
citation validator. It proves the graph side of the demo works before any Gemini key exists.

Needs the Kettle graph loaded with fake embeddings:
    LORE_FAKE_EMBEDDINGS=true uv run python -m lore.loader.load --reset
"""

from __future__ import annotations

import re

import pytest

from lore.agents.base import FindingsDraft
from lore.agents.supervisor import ReportDraft, run_investigation
from lore.llm import FakeLLM, LLMResponse
from lore.models import StepEvent
from lore.permissions import viewer_for

pytestmark = pytest.mark.integration

# What each agent "decides" to do, in order. Args never contain a viewer.
PLANS = {
    "Triage": [("blast_radius", {"service": "checkout"}), ("service_criticality", {})],
    "Historian": [
        ("similar_incidents", {"symptom": "checkout latency pricing overload"}),
        ("trace_decision", {"entity": "svc:pricing"}),
    ],
    "Investigator": [
        ("recent_changes", {"service": "checkout", "hours": 24}),
        ("evidence_path", {"alert_id": "A-3001", "pr_number": "482"}),
    ],
    "Responder": [("who_knows", {"service": "pricing"})],
}
WANTED = [
    "pr:482",
    "pr:479",
    "adr:011",
    "inc:INC-0307",
    "thread:pricing-private-0142",
    "svc:pricing",
]


def _agent(system: str) -> str:
    return next(name for name in PLANS if name in system.split(".")[0])


def _allowed_ids(contents) -> list[str]:
    text = contents[0].parts[0].text
    match = re.search(r"(?:Ids you may cite|Allowed ids): \[(.*?)\]", text)
    return re.findall(r"'([^']+)'", match.group(1)) if match else []


def scripted_model(model, system, contents, tools, response_schema) -> LLMResponse:
    if response_schema is FindingsDraft:
        allowed = _allowed_ids(contents)
        cited = [i for i in WANTED if i in allowed] or allowed[:1]
        root = "pr:482" if "pr:482" in allowed and "Investigator" in system else None
        findings = [{"text": f"Evidence points at {i}.", "citations": [i]} for i in cited]
        return FakeLLM.structured({"findings": findings, "confidence": 0.9, "root_cause": root})
    if response_schema is ReportDraft:
        allowed = _allowed_ids(contents)
        return FakeLLM.structured(
            {
                "summary": "PR #482 lowered the pricing cache TTL; checkout slowed.",
                "root_cause": "pr:482",
                "rejected_suspects": [
                    {"text": "PR #479 only changed copy.", "citations": ["pr:479"]}
                ],
                "claims": [
                    {"text": f"Cited {i}.", "citations": [i]} for i in WANTED if i in allowed
                ]
                + [{"text": "An invented fact.", "citations": ["pr:999"]}],
                "people": {"page": "person:rahul", "consult": ["person:marco"], "notify": []},
            }
        )
    plan = PLANS[_agent(system)]
    turn = (len(contents) - 1) // 2  # opening message, then (model call, tool replies) pairs
    if turn < len(plan):
        tool, args = plan[turn]
        return FakeLLM.call(tool, reason=f"scripted step {turn}", **args)
    return FakeLLM.answer("Done.")


async def _run(persona: str):
    from lore.db import GraphClient

    events: list[StepEvent] = []

    async def emit(event: StepEvent) -> None:
        events.append(event)

    llm = FakeLLM(default=scripted_model)
    report, summary = await run_investigation(
        "alert:A-3001", viewer_for(persona), llm=llm, graph=GraphClient(), emit=emit
    )
    return report, summary, events, llm


async def test_story_a_as_arjun_finds_pr_482_and_hides_the_private_thread(falkordb_available):
    report, summary, events, llm = await _run("arjun")

    assert report.root_cause == "pr:482"
    assert report.severity == "P1"  # tier-1 checkout is in the blast radius: set by code
    assert report.evidence_path == [
        "alert:A-3001",
        "svc:checkout",
        "svc:promo-engine",
        "svc:pricing",
        "deploy:991",
        "pr:482",
    ]
    assert report.people.page == "person:rahul" and report.people.consult == ["person:marco"]
    assert [c.citations for c in report.dropped_claims] == [["pr:999"]]  # invented id dropped
    assert report.restricted_matches >= 1  # ADR-011's private discussion exists...
    every_id = {i for e in events for i in e.payload.get("node_ids", [])}
    assert "thread:pricing-private-0142" not in every_id  # ...but Arjun never receives it
    assert all(c.citations != ["thread:pricing-private-0142"] for c in report.claims)

    assert events[0].type == "investigation_started" and events[-1].type == "done"
    assert [e.seq for e in events] == sorted(e.seq for e in events)
    assert summary.steps >= 7
    sent_to_model = " ".join(str(call["contents"]) for call in llm.calls)
    assert "person:arjun" not in sent_to_model  # the viewer is never shown to the model


async def test_confirmed_story_a_teaches_a_playbook_that_story_b_can_recall(falkordb_available):
    """Plan section 8, procedural memory: ✅ on Story A -> Playbook -> found for Story B."""
    from lore import memory
    from lore.db import GraphClient
    from lore.llm import fake_embedding
    from lore.memory import PlaybookDraft

    report, _, events, _ = await _run("arjun")
    inv_id = events[0].investigation_id

    def summarise(model, system, contents, tools, response_schema):
        assert response_schema is PlaybookDraft
        return FakeLLM.structured(
            {
                "name": "Latency after a cache TTL change in a dependency",
                "symptom_pattern": "service assignment latency after a config cache ttl change",
                "steps": ["recent_changes", "evidence_path", "trace_decision", "made_up_tool"],
            }
        )

    graph = GraphClient()
    playbook_id = await memory.apply_feedback(graph, FakeLLM(default=summarise), inv_id, True)
    assert playbook_id == f"playbook:{inv_id.split(':')[-1]}"

    found = memory.find_playbooks(graph, fake_embedding("dispatch assignment latency"), k=5)
    mine = next(p for p in found if p["id"] == playbook_id)
    assert mine["steps"] == ["recent_changes", "evidence_path", "trace_decision"]  # no invented


async def test_story_a_as_dana_can_cite_the_private_thread(falkordb_available):
    report, _, events, _ = await _run("dana")
    assert report.root_cause == "pr:482"
    cited = {i for c in report.claims for i in c.citations}
    assert "thread:pricing-private-0142" in cited
