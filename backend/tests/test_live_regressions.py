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


def test_post_audience_blocks_a_private_citation_in_incidents(graph):
    blocked = check_post_audience(graph, "#incidents", [PRIVATE, "pr:482"])
    allowed = check_post_audience(graph, "#incidents", ["pr:482", "adr:011"])
    assert not blocked.allowed and PRIVATE in blocked.reason
    assert allowed.allowed


def test_ask_graph_facts_never_show_restricted_nodes_or_neighbours(graph):
    """FIX_LOG F-06: Ask's graph facts go through the same permission rule."""
    from lore.retrieval import entity_facts

    secret = {
        PRIVATE,
        "thread:pricing-private-0150",
        "inc:INC-0326",
        "thread:hr-private-0003",
        "thread:sec-incidents-0007",
    }
    asked = sorted(secret) + ["adr:011", "svc:pricing", "person:marco", "pr:482"]
    for persona in ("arjun", "sam", "marco"):
        found = entity_facts(_ctx(persona, graph), asked)
        seen = {c.id for c in found} | {i for c in found for i in c.related_ids}
        assert not seen & secret, (persona, seen & secret)
    sam_ids = {c.id for c in entity_facts(_ctx("sam", graph), asked)}
    assert "pr:482" not in sam_ids and "adr:011" not in sam_ids  # internal: not for contractors
    dana = entity_facts(_ctx("dana", graph), [PRIVATE])
    assert [c.id for c in dana] == [PRIVATE]  # allowed through incident-commander
