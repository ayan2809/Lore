"""Permission leak tests against a real FalkorDB with the Kettle graph loaded.

For every persona we run every content tool and every search, then check that no restricted id
from the story bible (section 4 table) appears ANYWHERE in the results: not in node_ids, not in
the data, not in the Cypher parameters echoed back. The queries use the stored embedding of the
restricted chunk itself, so the restricted source would be the top match if the filter failed.

Skipped automatically when FalkorDB is not reachable (see conftest.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from lore import graph_view, retrieval, tools
from lore.db import GraphClient
from lore.permissions import PERSONAS, viewer_for
from lore.tools import ToolContext, call_tool

pytestmark = pytest.mark.integration

RESTRICTED = {
    "thread:pricing-private-0142",
    "thread:pricing-private-0150",
    "inc:INC-0326",
    "thread:sec-incidents-0007",
}
HR = {"thread:hr-private-0003"}  # no persona may ever see it
# Story-bible section 4: what each persona must NOT get back.
FORBIDDEN = {
    "arjun": RESTRICTED | HR,
    "dana": HR,
    "sam": RESTRICTED | HR | {"adr:011"},
    "marco": RESTRICTED | HR,
}
TARGETS = sorted(RESTRICTED | HR | {"adr:011"})
ALERT_TIME = int(
    datetime(2026, 10, 14, 3, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))).timestamp()
)


@pytest.fixture(scope="module")
def graph() -> GraphClient:
    return GraphClient()


@pytest.fixture(scope="module")
def stored(graph):
    """For each target source: its chunk embedding and text, read as an admin (no filter)."""
    found = {}
    for source_id in TARGETS:
        rows = graph.ro(
            "MATCH (c:Chunk)-[:PART_OF]->(s {id: $id}) RETURN c.embedding, c.text LIMIT 1",
            {"id": source_id},
        ).rows
        if rows:
            found[source_id] = ([float(x) for x in rows[0][0]], rows[0][1])
    assert found, "the Kettle graph is not loaded (no chunks found for the restricted sources)"
    return found


def ctx_for(graph, persona: str, **kwargs) -> ToolContext:
    return ToolContext(viewer=viewer_for(persona), graph=graph, now_ts=ALERT_TIME, **kwargs)


def assert_clean(persona: str, payload) -> None:
    if isinstance(payload, dict):
        # `cypher` echoes the query text the caller wrote (run_cypher), not data from the graph.
        payload = {k: v for k, v in payload.items() if k != "cypher"}
    text = json.dumps(payload, default=str)
    for secret in FORBIDDEN[persona]:
        assert secret not in text, f"{persona} received {secret}"


@pytest.fixture(autouse=True)
def _reset_embedder():
    yield
    tools.set_embedder(None)


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_searches_never_return_forbidden_sources(graph, stored, persona):
    ctx = ctx_for(graph, persona)
    for qvec, text in stored.values():
        by_meaning = retrieval.vector_search(ctx, qvec, 20)
        by_words = retrieval.fulltext_search(ctx, " ".join(text.split()[:6]), 20)
        nearby = retrieval.graph_scoped_search(ctx, "svc:pricing", qvec, 20)
        hidden, _ = retrieval.restricted_match_count(ctx, qvec)
        for found in (by_meaning, by_words, nearby):
            assert_clean(persona, [c.model_dump() for c in found])
        assert isinstance(hidden, int)


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_every_tool_is_clean(graph, stored, persona):
    for source_id, (qvec, text) in stored.items():
        tools.set_embedder(lambda _text, v=qvec: v)
        ctx = ctx_for(graph, persona)
        calls = [
            ("search_discussions", {"query": text[:80], "service": "pricing"}),
            ("similar_incidents", {"symptom": text[:80]}),
            ("find_entity", {"name": source_id}),
            ("trace_decision", {"entity": "adr:011"}),
            ("trace_decision", {"entity": "pricing"}),
            ("who_knows", {"service": "pricing"}),
            ("who_knows", {"service": "payments-gateway"}),
            ("recent_changes", {"service": "checkout", "hours": 48}),
            ("evidence_path", {"alert_id": "A-3001", "pr_number": "482"}),
            ("blast_radius", {"service": "pricing"}),
            ("run_cypher", {"cypher": f"MATCH (n) WHERE n.id = '{source_id}' RETURN n.id AS id"}),
            (
                "run_cypher",
                {"cypher": "MATCH (n) WHERE n.access_level IS NOT NULL RETURN n.id AS id"},
            ),
        ]
        for name, args in calls:
            result = call_tool(ctx, name, {"reason": "leak test", **args})
            assert_clean(persona, result.model_dump())
        assert_clean(persona, sorted(ctx.seen_ids))


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_source_detail_and_graph_view_are_clean(graph, persona):
    ctx = ctx_for(graph, persona)
    for source_id in FORBIDDEN[persona]:
        assert graph_view.source_detail(ctx, source_id) is None, f"{persona} can open {source_id}"
    for center in ("svc:pricing", "adr:011", "inc:INC-0307", "svc:payments-gateway"):
        view = graph_view.neighbourhood(ctx, center, hops=3, limit=500)
        assert_clean(persona, view.model_dump())


def test_positive_controls_so_the_tests_are_not_vacuous(graph):
    dana, arjun, marco, sam = (ctx_for(graph, p) for p in ("dana", "arjun", "marco", "sam"))
    assert graph_view.source_detail(dana, "thread:pricing-private-0142") is not None
    assert graph_view.source_detail(dana, "inc:INC-0326") is not None
    assert graph_view.source_detail(dana, "thread:hr-private-0003") is None
    for ctx in (arjun, marco):
        assert graph_view.source_detail(ctx, "adr:011") is not None
        assert graph_view.source_detail(ctx, "thread:pricing-private-0142") is None
    assert graph_view.source_detail(sam, "adr:011") is None


def test_marcos_access_ended_when_he_changed_teams(graph):
    """WAS_MEMBER_OF / WAS_IN_CHANNEL grant nothing: only current relationships count."""
    old = graph.ro(
        "MATCH (:Person {id: 'person:marco'})-[r:WAS_MEMBER_OF]->(:Team {id: 'team:pricing'}) "
        "RETURN count(r)"
    ).rows[0][0]
    assert old == 1
    assert graph_view.source_detail(ctx_for(graph, "marco"), "thread:pricing-private-0142") is None


def test_arjun_gets_a_restricted_warning_but_dana_does_not(graph, stored):
    qvec, text = stored["thread:pricing-private-0142"]
    tools.set_embedder(lambda _text: qvec)
    arjun = call_tool(
        ctx_for(graph, "arjun"), "search_discussions", {"reason": "x", "query": text[:80]}
    )
    dana = call_tool(
        ctx_for(graph, "dana"), "search_discussions", {"reason": "x", "query": text[:80]}
    )
    assert arjun.restricted_matches >= 1
    assert "thread:pricing-private-0142" in dana.node_ids
    assert "thread:pricing-private-0142" not in str(arjun.model_dump())


def test_contractor_search_results_are_all_public(graph, stored):
    for qvec, _ in stored.values():
        found = retrieval.vector_search(ctx_for(graph, "sam"), qvec, 30)
        assert all(c.access_level == "public" for c in found)
