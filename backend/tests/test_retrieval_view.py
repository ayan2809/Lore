"""retrieval.py and graph_view.py over a fake graph (no FalkorDB needed)."""

from __future__ import annotations

import pytest

from lore import graph_view, retrieval
from tests.fakes import outcome

SEARCH_HEADER = [
    "id",
    "label",
    "source",
    "title",
    "updated_at",
    "access_level",
    "service",
    "text",
    "chunk_id",
    "score",
]


def test_distance_becomes_a_similarity_between_zero_and_one():
    assert retrieval.distance_to_similarity(0.0) == 1.0
    assert retrieval.distance_to_similarity(0.25) == pytest.approx(0.75)
    assert retrieval.distance_to_similarity(1.7) == 0.0
    assert retrieval.distance_to_similarity(-0.1) == 1.0


def test_clean_fulltext_drops_punctuation_and_stopwords():
    assert retrieval.clean_fulltext("Why is ADR-011 set to 300s?") == "ADR | 011 | set | 300s"
    assert retrieval.clean_fulltext("???") == ""


def test_vector_search_returns_candidates_with_a_meaning_signal(make_ctx, fake_graph):
    fake_graph.on(
        "vector_search_permitted:",
        outcome(
            SEARCH_HEADER,
            [
                "adr:011",
                "Decision",
                "adr",
                "TTL",
                5,
                "internal",
                "pricing",
                "Keep 300s",
                "adr:011#0",
                0.2,
            ],
        ),
    )
    [c] = retrieval.vector_search(make_ctx(), [0.1] * 3, k=5)
    assert (c.id, c.chunk_id) == ("adr:011", "adr:011#0")
    assert c.meaning == pytest.approx(0.8) and c.keyword == 0.0
    params = fake_graph.params_for("vector_search_permitted:")
    assert params["k"] == 5 and params["fetch_k"] == retrieval.FETCH_K
    assert params["viewer"] == "person:arjun"


def test_fulltext_search_skips_empty_queries(make_ctx, fake_graph):
    assert retrieval.fulltext_search(make_ctx(), "???") == []
    assert fake_graph.calls == []


def test_fulltext_search_keeps_the_raw_score(make_ctx, fake_graph):
    fake_graph.on(
        "fulltext_search_permitted:",
        outcome(
            SEARCH_HEADER,
            ["adr:011", "Decision", "adr", "TTL", 5, "internal", "pricing", "t", "c", 4.2],
        ),
    )
    [c] = retrieval.fulltext_search(make_ctx(), "ADR-011")
    assert c.keyword == 4.2 and c.meaning == 0.0
    assert fake_graph.params_for("fulltext_search_permitted:")["text"] == "ADR | 011"


def test_graph_scoped_search_turns_hops_into_closeness(make_ctx, fake_graph):
    fake_graph.on(
        "graph_scoped_search:",
        outcome(
            [*SEARCH_HEADER, "hops"],
            ["a", "Thread", "slack", "t", 1, "internal", "pricing", "x", "a#0", 0.1, 0],
            ["b", "Thread", "slack", "t", 1, "internal", "menu", "x", "b#0", 0.1, 2],
        ),
    )
    a, b = retrieval.graph_scoped_search(make_ctx(), "svc:pricing", [0.1], k=5)
    assert a.graph == 1.0 and b.graph == pytest.approx(1 / 3)


def test_restricted_match_count_names_the_team_and_lead(make_ctx, fake_graph):
    fake_graph.on(
        "restricted_match_count:",
        outcome(
            ["team", "team_name", "lead", "matches"],
            ["pricing", "pricing", "Rahul Verma", 2],
            ["security", None, None, 1],
        ),
    )
    count, hint = retrieval.restricted_match_count(make_ctx(), [0.1])
    assert count == 3 and hint == "ask the Pricing team (Rahul Verma)"


def test_restricted_match_count_with_nothing_hidden(make_ctx):
    assert retrieval.restricted_match_count(make_ctx(), [0.1]) == (0, None)


# ------------------------------------------------------------------ graph_view


def test_neighbourhood_builds_nodes_and_links(make_ctx, fake_graph):
    header = [
        "a_id",
        "a_label",
        "a_name",
        "a_access",
        "a_props",
        "rel",
        "b_id",
        "b_label",
        "b_name",
        "b_access",
        "b_props",
    ]
    fake_graph.on(
        "graph_neighbourhood:",
        outcome(
            header,
            [
                "svc:checkout",
                "Service",
                "checkout",
                None,
                {"tier": 1, "team": None},
                "DEPENDS_ON",
                "svc:promo-engine",
                "Service",
                "promo-engine",
                None,
                {"tier": 2},
            ],
            [
                "svc:promo-engine",
                "Service",
                "promo-engine",
                None,
                {"tier": 2},
                "DEPENDS_ON",
                "svc:pricing",
                "Service",
                "pricing",
                None,
                {"tier": 1},
            ],
        ),
    )
    view = graph_view.neighbourhood(make_ctx(), "svc:checkout", hops=9, limit=50)
    assert {n.id for n in view.nodes} == {"svc:checkout", "svc:promo-engine", "svc:pricing"}
    assert len(view.links) == 2 and view.links[0].type == "DEPENDS_ON"
    assert view.nodes[0].props == {"tier": 1}  # None values are dropped
    cypher, params = fake_graph.calls[0]
    assert "__HOPS__" not in cypher and "*1..3]" in cypher  # hops capped at 3
    assert params["limit"] == 50 and params["viewer"] == "person:arjun"


def test_source_detail_joins_chunks_and_hides_what_is_not_visible(make_ctx, fake_graph):
    header = [
        "id",
        "label",
        "source",
        "title",
        "updated_at",
        "access_level",
        "team",
        "service",
        "chunks",
    ]
    fake_graph.on(
        "source_detail:",
        outcome(
            header,
            [
                "adr:011",
                "Decision",
                "adr",
                "TTL",
                5,
                "internal",
                "pricing",
                "pricing",
                ["First part.", "Second part."],
            ],
        ),
    )
    detail = graph_view.source_detail(make_ctx(), "adr:011")
    assert detail["text"] == "First part.\n\nSecond part." and "chunks" not in detail
    fake_graph.canned["source_detail:"] = outcome(header)
    assert graph_view.source_detail(make_ctx("sam"), "adr:011") is None


def test_list_alerts_and_alert_context(fake_graph):
    fake_graph.on(
        "list_alerts:",
        outcome(
            ["id", "name", "symptom", "service", "started_at"],
            ["alert:A-3001", "checkout p99 latency > 3s", "latency", "svc:checkout", 100],
        ),
    )
    assert graph_view.list_alerts(fake_graph)[0]["service"] == "svc:checkout"
    fake_graph.on(
        "alert_context:",
        outcome(
            ["id", "name", "symptom", "started_at", "service", "service_name", "tier"],
            ["alert:A-3001", "n", "s", 100, "svc:checkout", "checkout", 1],
        ),
    )
    ctx = graph_view.alert_context(fake_graph, "A-3001")
    assert ctx["tier"] == 1 and fake_graph.params_for("alert_context:") == {"alert": "alert:A-3001"}
