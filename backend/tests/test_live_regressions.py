"""Regression tests for problems found by running the queries on a live FalkorDB (Oct 16).

See docs/STATE.md C-02: FalkorDB 4.18 errors on a path pattern in a WHERE attached to a WITH that
computes a new value. These checks fail loudly if a query falls back into that shape.
"""

from __future__ import annotations

import pytest

from lore.permissions import viewer_for
from lore.policy import check_post_audience
from lore.tools import ToolContext, call_tool

pytestmark = pytest.mark.integration

PRIVATE = "thread:pricing-private-0142"


@pytest.fixture
def graph(falkordb_available):
    from lore.db import GraphClient

    return GraphClient()


def _ctx(persona, graph):
    return ToolContext(viewer=viewer_for(persona), graph=graph)


def test_find_entity_finds_a_restricted_thread_only_for_those_allowed(graph):
    dana = call_tool(_ctx("dana", graph), "find_entity", {"reason": "t", "name": PRIVATE})
    arjun = call_tool(_ctx("arjun", graph), "find_entity", {"reason": "t", "name": PRIVATE})
    assert dana.error is None and PRIVATE in dana.node_ids
    assert arjun.error is None and PRIVATE not in arjun.node_ids


def test_run_cypher_never_returns_memory_nodes_or_restricted_ids(graph):
    sam = _ctx("sam", graph)
    for cypher in [
        "MATCH (f:Finding) RETURN f.id AS id, f",
        "MATCH (s:Step) RETURN s.id AS id, s.node_ids AS n",
        f"MATCH (t:Thread {{id: '{PRIVATE}'}}) RETURN t.id AS id, t.title AS title",
    ]:
        result = call_tool(sam, "run_cypher", {"reason": "t", "cypher": cypher})
        assert result.error is None, cypher
        assert result.data == [], cypher


def test_post_audience_blocks_a_private_citation_in_incidents(graph):
    blocked = check_post_audience(graph, "#incidents", [PRIVATE, "pr:482"])
    allowed = check_post_audience(graph, "#incidents", ["pr:482", "adr:011"])
    assert not blocked.allowed and PRIVATE in blocked.reason
    assert allowed.allowed
