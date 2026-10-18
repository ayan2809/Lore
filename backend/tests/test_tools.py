"""Tool registry, permission plumbing and each tool's shaping of results (no FalkorDB needed)."""

from __future__ import annotations

import re

import pytest

from lore import tools
from lore.db import QUERIES_DIR, load_query
from lore.models import Action
from lore.tools import REGISTRY, call_tool, run_query
from tests.fakes import FakeGraph, outcome

EXPECTED_MODES = {
    "find_entity": {"graph", "vector"},
    "blast_radius": {"graph"},
    "service_criticality": {"graph"},
    "similar_incidents": {"graph", "vector"},
    "get_playbook": {"graph"},
    "search_discussions": {"graph", "vector"},
    "recent_changes": {"graph"},
    "evidence_path": {"graph"},
    "trace_decision": {"graph"},
    "who_knows": {"graph"},
    "propose_action": {"graph", "vector"},
}

# Query files that return content (sources, chunks, threads, tickets, docs, incidents, PRs).
CONTENT_QUERIES = [
    "find_entity",
    "similar_incidents",
    "vector_search_permitted",
    "fulltext_search_permitted",
    "graph_scoped_search",
    "restricted_match_count",
    "recent_changes",
    "evidence_path",
    "evidence_path_fallback",
    "trace_decision",
    "who_knows",
    "graph_neighbourhood",
    "source_detail",
]
# Checks the permission of each channel reader instead of the viewer, so it has no $viewer.
AUDIENCE_QUERIES = ["post_audience_check", "policy_restricted_citations"]  # policy checks
# Files owned by this work package (the memory_/action_ files belong to other agents).
MY_QUERIES = (
    CONTENT_QUERIES
    + AUDIENCE_QUERIES
    + [
        "blast_radius",
        "pagerank_services",
        "get_playbook",
        "list_alerts",
        "alert_context",
        "channel_info",
    ]
)


def fake_embedder(text: str) -> list[float]:
    return [0.1, 0.2, 0.3]


@pytest.fixture(autouse=True)
def _embedder():
    tools.set_embedder(fake_embedder)
    yield
    tools.set_embedder(None)


# ------------------------------------------------------------------ registry


def test_every_expected_tool_is_registered_with_the_right_modes():
    assert set(EXPECTED_MODES) <= set(REGISTRY)
    for name, modes in EXPECTED_MODES.items():
        assert set(REGISTRY[name].modes) == modes, name


def test_every_tool_requires_a_reason_and_hides_the_viewer():
    for name, spec in REGISTRY.items():
        fields = spec.args_model.model_fields
        assert "reason" in fields, name
        assert fields["reason"].is_required(), name
        assert "viewer" not in fields and "open_levels" not in fields, name


def test_tool_descriptions_are_written_for_the_model():
    for name, spec in REGISTRY.items():
        assert len(spec.description) > 40, name


def test_tools_for_filters_by_mode():
    names = list(EXPECTED_MODES)
    graph_off = {s.name for s in tools.tools_for(names, "vector")}
    assert graph_off == {n for n, m in EXPECTED_MODES.items() if "vector" in m}


# ------------------------------------------------------------------ query files


@pytest.mark.parametrize("name", MY_QUERIES)
def test_query_files_start_with_a_comment_and_are_read_only(name):
    text = load_query(name)
    assert text.startswith(f"// {name}:"), "first line must name the query (FakeGraph keys on it)"
    code = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("//"))
    assert not re.search(r"\b(CREATE|MERGE|DELETE|REMOVE|DROP)\b|\bSET\s", code), name


@pytest.mark.parametrize("name", CONTENT_QUERIES)
def test_content_queries_carry_the_permission_filter(name):
    text = load_query(name)
    assert "$open_levels" in text, name
    assert "VISIBLE_TO" in text, name
    assert "$viewer" in text, name


def test_post_audience_check_tests_each_reader_not_the_viewer():
    text = load_query("post_audience_check")
    assert "VISIBLE_TO" in text and "IN_CHANNEL" in text and "$cited_ids" in text


def test_content_query_list_covers_every_file_that_reads_access_level():
    for path in QUERIES_DIR.glob("*.cypher"):
        if path.stem.startswith(("memory_", "action_", "ask_")):
            continue
        if "access_level" in path.read_text():
            tested = CONTENT_QUERIES + AUDIENCE_QUERIES
            assert path.stem in tested, f"{path.stem} reads access_level but is not tested"


# ------------------------------------------------------------------ permission plumbing


def test_permission_params_are_merged_last(make_ctx, fake_graph):
    ctx = make_ctx("arjun")
    run_query(ctx, "find_entity", {"viewer": "person:dana", "open_levels": ["confidential"]})
    params = fake_graph.params_for("find_entity:")
    assert params["viewer"] == "person:arjun"
    assert params["open_levels"] == ["public", "internal"]


def test_model_supplied_viewer_is_ignored_by_call_tool(make_ctx, fake_graph):
    ctx = make_ctx("sam")
    raw = {"reason": "r", "name": "pricing", "viewer": "person:dana", "open_levels": ["restricted"]}
    result = call_tool(ctx, "find_entity", raw)
    assert result.error is None
    params = fake_graph.params_for("find_entity:")
    assert params["viewer"] == "person:sam"
    assert params["open_levels"] == ["public"]


def test_unknown_tool_and_bad_args_return_errors_not_exceptions(make_ctx):
    ctx = make_ctx()
    assert call_tool(ctx, "nope", {"reason": "x"}).error == "unknown tool"
    bad = call_tool(ctx, "blast_radius", {"reason": "x"})  # missing service
    assert bad.error and bad.error.startswith("bad args")


def test_a_failing_query_becomes_a_tool_error(make_ctx, fake_graph):
    def boom(cypher, params):
        raise RuntimeError("timeout")

    fake_graph.on("blast_radius:", boom)
    result = call_tool(make_ctx(), "blast_radius", {"reason": "x", "service": "checkout"})
    assert result.error == "RuntimeError: timeout"


def test_graph_only_tools_are_refused_in_vector_mode(make_ctx):
    ctx = make_ctx(mode="vector")
    result = call_tool(ctx, "blast_radius", {"reason": "x", "service": "checkout"})
    assert "not available" in result.error


def test_seen_ids_grow_with_returned_node_ids(make_ctx, fake_graph):
    fake_graph.on(
        "find_entity:",
        outcome(
            ["id", "label", "name", "tier", "access_level", "owner_team"],
            ["svc:pricing", "Service", "pricing", 1, None, "team:pricing"],
        ),
    )
    ctx = make_ctx()
    result = call_tool(ctx, "find_entity", {"reason": "x", "name": "pricing"})
    assert {"svc:pricing", "team:pricing"} <= ctx.seen_ids
    assert result.edges[0].model_dump() == {
        "source": "team:pricing",
        "target": "svc:pricing",
        "type": "OWNS",
    }


# ------------------------------------------------------------------ id helpers


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ADR-011", "adr:011"),
        ("adr 11", "adr:011"),
        ("PR #482", "pr:482"),
        ("pr-482", "pr:482"),
        ("INC-0307", "inc:INC-0307"),
        ("prc-311", "ticket:PRC-311"),
        ("A-3001", "alert:A-3001"),
        ("deploy 991", "deploy:991"),
        ("Pricing", "svc:pricing"),
        ("svc:ledger", "svc:ledger"),
        ("person:arjun", "person:arjun"),
    ],
)
def test_normalise_id(text, expected):
    assert tools.normalise_id(text) == expected


# ------------------------------------------------------------------ individual tools


def test_blast_radius_turns_paths_into_edges(make_ctx, fake_graph):
    fake_graph.on(
        "blast_radius:",
        outcome(
            ["id", "name", "tier", "hops", "via"],
            ["svc:pricing", "pricing", 1, 0, ["svc:pricing"]],
            ["svc:promo-engine", "promo-engine", 2, 1, ["svc:pricing", "svc:promo-engine"]],
            ["svc:checkout", "checkout", 1, 2, ["svc:pricing", "svc:promo-engine", "svc:checkout"]],
        ),
    )
    result = call_tool(make_ctx(), "blast_radius", {"reason": "x", "service": "Pricing"})
    assert fake_graph.params_for("blast_radius:")["service"] == "svc:pricing"
    assert result.node_ids == ["svc:pricing", "svc:promo-engine", "svc:checkout"]
    pairs = {(e.source, e.target, e.type) for e in result.edges}
    assert pairs == {
        ("svc:promo-engine", "svc:pricing", "DEPENDS_ON"),
        ("svc:checkout", "svc:promo-engine", "DEPENDS_ON"),
    }
    assert "//" not in result.cypher  # the trail shows the query without its comment header


def test_recent_changes_computes_since_from_the_alert_time(make_ctx, fake_graph):
    ctx = make_ctx(now_ts=1_000_000)
    call_tool(ctx, "recent_changes", {"reason": "x", "service": "checkout", "hours": 2})
    params = fake_graph.params_for("recent_changes:")
    assert params["until"] == 1_000_000
    assert params["since"] == 1_000_000 - 2 * 3600


def test_recent_changes_returns_suspects_with_edges(make_ctx, fake_graph):
    fake_graph.on(
        "recent_changes:",
        outcome(
            [
                "service_id",
                "service",
                "hops",
                "deploy_id",
                "deployed_at",
                "pr_id",
                "pr_number",
                "pr_title",
                "access_level",
                "author_id",
                "author",
                "modules",
            ],
            [
                "svc:pricing",
                "pricing",
                2,
                "deploy:991",
                5,
                "pr:482",
                482,
                "Lower TTL",
                "internal",
                "person:priya",
                "Priya Nair",
                ["mod:pricing/config.yaml"],
            ],
        ),
    )
    result = call_tool(
        make_ctx(now_ts=10), "recent_changes", {"reason": "x", "service": "checkout"}
    )
    assert "pr:482" in result.node_ids and "mod:pricing/config.yaml" in result.node_ids
    kinds = {e.type for e in result.edges}
    assert kinds == {"DEPLOYED_TO", "INCLUDES", "AUTHORED", "MODIFIES"}


def test_evidence_path_keeps_the_order(make_ctx, fake_graph):
    ids = [
        "alert:A-3001",
        "svc:checkout",
        "svc:promo-engine",
        "svc:pricing",
        "deploy:991",
        "pr:482",
    ]
    fake_graph.on(
        "evidence_path:",
        outcome(
            ["node_ids", "rel_sources", "rel_targets", "rel_types", "weight"],
            [
                ids,
                ["alert:A-3001", "svc:checkout", "svc:promo-engine", "deploy:991", "deploy:991"],
                ["svc:checkout", "svc:promo-engine", "svc:pricing", "svc:pricing", "pr:482"],
                ["FIRED_ON", "DEPENDS_ON", "DEPENDS_ON", "DEPLOYED_TO", "INCLUDES"],
                5,
            ],
        ),
    )
    result = call_tool(
        make_ctx(), "evidence_path", {"reason": "x", "alert_id": "A-3001", "pr_number": "#482"}
    )
    params = fake_graph.params_for("evidence_path:")
    assert params["alert"] == "alert:A-3001" and params["pr"] == "pr:482"
    assert result.node_ids == ids
    assert result.data[0]["length"] == 5
    assert result.edges[0].type == "FIRED_ON" and result.edges[-1].type == "INCLUDES"


def test_evidence_path_falls_back_when_spp_aths_fails(make_ctx, fake_graph):
    def boom(cypher, params):
        raise RuntimeError("weightProp")

    fake_graph.on("evidence_path:", boom)
    fake_graph.on(
        "evidence_path_fallback:",
        outcome(
            ["node_ids", "rel_sources", "rel_targets", "rel_types", "weight"],
            [["alert:A-3001", "svc:checkout"], ["alert:A-3001"], ["svc:checkout"], ["FIRED_ON"], 1],
        ),
    )
    result = call_tool(
        make_ctx(), "evidence_path", {"reason": "x", "alert_id": "A-3001", "pr_number": "482"}
    )
    assert result.error is None and result.node_ids == ["alert:A-3001", "svc:checkout"]


def _expert(id_, name, code, inc, team, owner, on_owner, lead, authored=0):
    return [id_, name, code, inc, authored, code + inc, team, owner, on_owner, lead]


EXPERT_HEADER = [
    "id",
    "name",
    "code_score",
    "incident_score",
    "authored",
    "score",
    "current_team",
    "owner_team",
    "on_owner_team",
    "is_lead",
]


def test_who_knows_pages_the_owner_and_consults_marco(make_ctx, fake_graph):
    fake_graph.on(
        "who_knows:",
        outcome(
            EXPERT_HEADER,
            _expert("person:marco", "Marco", 90, 5, "team:data", "team:pricing", False, False, 30),
            _expert("person:priya", "Priya", 20, 0, "team:pricing", "team:pricing", True, False, 6),
            _expert("person:rahul", "Rahul", 4, 0, "team:pricing", "team:pricing", True, True, 0),
            _expert("person:rahul", "Rahul", 0, 0, "team:pricing", "team:pricing", True, True, 0),
        ),
    )
    result = call_tool(make_ctx(), "who_knows", {"reason": "x", "service": "pricing"})
    by_role = {}
    for p in result.data:
        by_role.setdefault(p["role"], []).append(p["id"])
    assert by_role["page"] == ["person:rahul"]
    assert by_role["consult"] == ["person:marco", "person:priya"]
    assert "person:marco" not in by_role["page"]
    assert any(e.source == "team:pricing" and e.type == "OWNS" for e in result.edges)


def test_who_knows_flags_a_bus_factor_of_one(make_ctx, fake_graph):
    fake_graph.on(
        "who_knows:",
        outcome(
            EXPERT_HEADER,
            _expert(
                "person:ines", "Ines", 60, 0, "team:payments", "team:payments", True, False, 20
            ),
            _expert("person:hana", "Hana", 8, 0, "team:payments", "team:payments", True, True, 0),
        ),
    )
    result = call_tool(make_ctx(), "who_knows", {"reason": "x", "service": "ledger"})
    assert all(p["bus_factor_1"] for p in result.data)


def test_search_discussions_vector_mode_skips_graph_searches(make_ctx, fake_graph):
    header = [
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
    fake_graph.on(
        "vector_search_permitted:",
        outcome(
            header,
            [
                "adr:011",
                "Decision",
                "adr",
                "TTL >= 300s",
                1_770_000_000,
                "internal",
                "pricing",
                "Keep the TTL at 300 seconds",
                "adr:011#0",
                0.1,
            ],
        ),
    )
    fake_graph.on(
        "restricted_match_count:",
        outcome(["team", "team_name", "lead", "matches"], ["pricing", "Pricing", "Rahul Verma", 1]),
    )
    result = call_tool(
        make_ctx(mode="vector"),
        "search_discussions",
        {"reason": "x", "query": "pricing cache TTL", "service": "pricing"},
    )
    assert fake_graph.count("fulltext_search_permitted:") == 0
    assert fake_graph.count("graph_scoped_search:") == 0
    assert result.node_ids == ["adr:011"]
    assert result.restricted_matches == 1
    assert result.restricted_owner_hint == "ask the Pricing team (Rahul Verma)"


def test_search_discussions_graph_mode_runs_all_three_searches(make_ctx, fake_graph):
    result = call_tool(
        make_ctx(mode="graph"),
        "search_discussions",
        {"reason": "x", "query": "pricing cache TTL", "service": "pricing"},
    )
    assert result.error is None
    for key in ("vector_search_permitted:", "fulltext_search_permitted:", "graph_scoped_search:"):
        assert fake_graph.count(key) == 1


def test_trace_decision_reports_hidden_threads_as_a_count_only(make_ctx, fake_graph):
    fake_graph.on(
        "trace_decision:",
        outcome(
            [
                "decision_id",
                "title",
                "updated_at",
                "access_level",
                "threads",
                "hidden_threads",
                "hidden_team",
                "supersedes",
                "superseded_by",
                "incidents",
            ],
            [
                "adr:011",
                "TTL",
                1,
                "internal",
                [],
                1,
                "pricing",
                ["wiki:pricing-cache"],
                [],
                [{"incident": "inc:INC-0307", "postmortem": "pm:INC-0307"}],
            ],
        ),
    )
    result = call_tool(make_ctx("arjun"), "trace_decision", {"reason": "x", "entity": "ADR-011"})
    assert fake_graph.params_for("trace_decision:")["entity"] == "adr:011"
    assert result.restricted_matches == 1
    assert "thread:pricing-private-0142" not in str(result.model_dump())
    assert "wiki:pricing-cache" in result.node_ids and "pm:INC-0307" in result.node_ids


def test_get_playbook_parses_the_steps(make_ctx, fake_graph):
    fake_graph.on(
        "get_playbook:",
        outcome(
            ["id", "name", "symptom_pattern", "steps", "success_count", "distance"],
            [
                "playbook:1",
                "TTL change",
                "latency after config change",
                '["recent_changes", "evidence_path"]',
                2,
                0.1,
            ],
        ),
    )
    result = call_tool(make_ctx(), "get_playbook", {"reason": "x", "symptom": "latency"})
    assert result.data[0]["steps"] == ["recent_changes", "evidence_path"]


def test_propose_action_calls_actions_propose(make_ctx, monkeypatch):
    from lore import actions

    seen = {}

    def fake_propose(**kwargs):
        seen.update(kwargs)
        return Action(
            id="action:1",
            investigation_id=kwargs["investigation_id"],
            kind=kwargs["kind"],
            target=kwargs["target"],
            text=kwargs["text"],
            cited_ids=kwargs["cited_ids"],
        )

    monkeypatch.setattr(actions, "propose", fake_propose)
    ctx = make_ctx(investigation_id="inv-1")
    ctx.seen_ids.add("adr:011")
    result = call_tool(
        ctx,
        "propose_action",
        {
            "reason": "x",
            "kind": "slack_post",
            "target": "#incidents",
            "text": "hi",
            "cited_ids": ["adr:011", "adr:999"],
        },
    )
    assert result.error is None
    assert seen["investigation_id"] == "inv-1" and seen["title"] is None
    assert result.data[0]["id"] == "action:1"
    assert result.data[0]["unverified_citations"] == ["adr:999"]


def test_graph_never_receives_a_write(make_ctx, fake_graph):
    assert isinstance(fake_graph, FakeGraph)
    with pytest.raises(AssertionError):
        fake_graph.write("CREATE (n)")


def test_a_missing_reason_does_not_fail_the_tool(make_ctx, fake_graph):
    """FIX_LOG F-17: small models sometimes drop `reason`; the call still runs."""
    from lore.tools import NO_REASON

    result = call_tool(make_ctx("arjun"), "service_criticality", {"top": 3})
    assert result.error is None and result.reason == NO_REASON
