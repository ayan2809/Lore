"""lore.memory against a fake graph that records every write (no FalkorDB)."""

from __future__ import annotations

import json
from typing import Any

from lore import memory
from lore.db import QueryOutcome, load_query
from lore.llm import FakeLLM
from lore.models import Claim, EdgeRef, ToolResult
from tests.fakes import FakeGraph, outcome


class MemoryGraph(FakeGraph):
    """FakeGraph that allows writes (memory is the one module that may write) and records them.
    Reads and writes share the same canned answers, keyed by the `// <query_name>:` header."""

    def __init__(self, canned=None):
        super().__init__(canned)
        self.writes: list[tuple[str, dict[str, Any]]] = []

    def write(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome:
        self.writes.append((cypher, params or {}))
        return self.ro(cypher, params)

    def written(self, query_name: str) -> list[dict[str, Any]]:
        """Params of every write that ran lore/queries/<query_name>.cypher, in order."""
        text = load_query(query_name)
        return [p for c, p in self.writes if c == text]

    def write_order(self) -> list[str]:
        return [c.split(":", 1)[0].removeprefix("// ") for c, _ in self.writes]


def test_record_step_stores_ids_as_array_and_edges_as_json():
    g = MemoryGraph()
    result = ToolResult(
        tool="blast_radius",
        reason="see the spread",
        cypher="MATCH ...",
        ms=3.21,
        node_ids=["svc:checkout", "svc:pricing"],
        edges=[EdgeRef(source="svc:checkout", target="svc:pricing", type="DEPENDS_ON")],
    )
    step_id = memory.record_step(g, "inv:1", 4, "triage", result)
    [params] = g.written("memory_record_step")
    assert step_id == "step:inv:1:4"
    assert params["node_ids"] == ["svc:checkout", "svc:pricing"]
    assert json.loads(params["edges"])[0]["type"] == "DEPENDS_ON"
    assert params["agent"] == "triage" and params["seq"] == 4


def test_record_finding_links_citations():
    g = MemoryGraph()
    memory.record_finding(g, "inv:1", "historian", Claim(text="t", citations=["inc:INC-0307"]), 0.8)
    [params] = g.written("memory_record_finding")
    assert params["citations"] == ["inc:INC-0307"] and params["confidence"] == 0.8


def test_update_expertise_closes_old_edge_then_opens_new_one():
    g = MemoryGraph({"memory_current_expertise:": outcome(["score"], [12.0])})
    changed = memory.update_expertise(g, "person:marco", "svc:pricing", 3.0, now=1_790_000_000)
    assert changed
    assert g.write_order() == ["memory_expertise_close", "memory_expertise_open"]
    [close] = g.written("memory_expertise_close")
    [new] = g.written("memory_expertise_open")
    assert close["now"] == new["now"] == 1_790_000_000  # old valid_to == new valid_from
    assert new["score"] == 3.0
    # history is never overwritten: no query in this path deletes or edits the score in place
    assert "DELETE" not in load_query("memory_expertise_close")
    assert "r.score" not in load_query("memory_expertise_close")


def test_update_expertise_skips_unchanged_score():
    g = MemoryGraph({"memory_current_expertise:": outcome(["score"], [3.0])})
    assert memory.update_expertise(g, "person:marco", "svc:pricing", 3.0) is False
    assert g.writes == []


async def test_feedback_confirm_without_playbook_learns_one():
    g = MemoryGraph(
        {
            "memory_feedback:": outcome(["used", "learned"], [[], []]),
            "memory_read_investigation:": outcome(
                ["symptom", "root_cause", "tools"],
                [
                    "checkout p99 latency",
                    "pr:482",
                    ["find_entity", "blast_radius", "recent_changes", "evidence_path"],
                ],
            ),
        }
    )
    draft = {
        "name": "Config TTL change in a dependency",
        "symptom_pattern": "latency spike after a config change downstream",
        "steps": ["recent_changes", "made_up_tool", "evidence_path"],
    }
    fake = FakeLLM([FakeLLM.structured(draft)], dim=8)
    playbook_id = await memory.apply_feedback(g, fake, "inv:abc", confirmed=True)

    assert playbook_id == "playbook:abc"
    [saved] = g.written("memory_save_playbook")
    assert json.loads(saved["steps"]) == ["recent_changes", "evidence_path"]  # no invented tools
    assert len(saved["embedding"]) == 8
    # The summariser sees tool names and the root-cause KIND only, not raw tool output.
    prompt = fake.calls[0]["contents"][0].parts[0].text
    assert "pr:482" not in prompt and "kind: pr" in prompt


async def test_feedback_adjusts_the_playbook_that_was_used():
    g = MemoryGraph({"memory_feedback:": outcome(["used", "learned"], [["playbook:a"], []])})
    assert await memory.apply_feedback(g, FakeLLM(), "inv:2", confirmed=False) == "playbook:a"
    [adjust] = g.written("memory_adjust_playbook")
    assert adjust == {"id": "playbook:a", "delta": -1}
    assert g.written("memory_save_playbook") == []


def test_find_playbooks_parses_json_steps():
    g = MemoryGraph(
        {
            "memory_find_playbooks:": outcome(
                ["id", "steps", "success_count", "distance"],
                ["playbook:a", '["recent_changes", "evidence_path"]', 2, 0.1],
            )
        }
    )
    [row] = memory.find_playbooks(g, [0.1] * 4)
    assert row["steps"] == ["recent_changes", "evidence_path"]


def test_query_trace_records_ids_not_text():
    g = MemoryGraph()
    trace_id = memory.record_query_trace(
        g,
        question="q",
        viewer_id="person:sam",
        mode="graph",
        retrieved_ids=["adr:011"],
        filtered_count=1,
        reranked_ids=["adr:011"],
        cited_ids=[],
        refused=True,
        ms=12.3,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
    )
    [params] = g.written("memory_query_trace")
    assert trace_id.startswith("query:") and params["filtered_count"] == 1
    assert "text" not in load_query("memory_query_trace").split("CREATE", 1)[1]
