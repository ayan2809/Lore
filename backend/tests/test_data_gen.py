"""Tests for the synthetic data: determinism, counts, links, permissions and the planted stories.

No FalkorDB needed: the generated JSON is checked as plain Python data. `can_see()` re-implements
the permission rule from plan section 6 so the data itself can be checked.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from lore.data_gen import generate, story
from lore.models import Viewer

DATA = generate.DATA_DIR
EVAL = Path(__file__).resolve().parents[1] / "eval"
SOURCE_LABELS = {"PR", "Thread", "Ticket", "Doc", "Decision", "Incident"}
PERSONAS = ["arjun", "dana", "sam", "marco"]


@pytest.fixture(scope="module")
def built():
    b = generate.build(text_dir=None)  # template text only, so tests do not depend on text/*.json
    return b


@pytest.fixture(scope="module")
def nodes(built):
    return built.nodes


@pytest.fixture(scope="module")
def edges(built):
    return list(built.edges.values())


def edge_set(edges, type_):
    return {(e["src"], e["dst"]) for e in edges if e["type"] == type_}


def can_see(person: str, source: str, nodes, edges) -> bool:
    """Plan section 6: open level, OR a current path person -> team/role/channel <- source."""
    node = nodes[source]["props"]
    p = nodes[person]["props"]
    viewer = Viewer(id=person, name=p["name"], employment=p["employment"])
    if node["access_level"] in viewer.open_levels:
        return True
    via = {e["dst"] for e in edges if e["src"] == person and e["type"] in
           ("MEMBER_OF", "HAS_ROLE", "IN_CHANNEL")}  # fmt: skip
    return any(e["src"] == source and e["type"] == "VISIBLE_TO" and e["dst"] in via for e in edges)


# ---------------------------------------------------------------- determinism and counts


def test_generation_is_deterministic(built):
    again = generate.build(text_dir=None)
    assert generate.dump(sorted(built.nodes.values(), key=lambda n: n["id"])) == generate.dump(
        sorted(again.nodes.values(), key=lambda n: n["id"])
    )
    assert [e for e in built.edges.values()] == [e for e in again.edges.values()]


def test_committed_files_match_the_generator():
    """backend/data/*.json must be what `python -m lore.data_gen.generate` writes today."""
    b = generate.build(DATA / "text")
    nodes = sorted(b.nodes.values(), key=lambda n: (n["label"], n["id"]))
    edges = sorted(b.edges.values(), key=lambda e: (e["type"], e["src"], e["dst"]))
    assert (DATA / "nodes.json").read_text(encoding="utf-8") == generate.dump(nodes)
    assert (DATA / "edges.json").read_text(encoding="utf-8") == generate.dump(edges)


def test_counts_match_the_story_bible(nodes):
    counts = Counter(n["label"] for n in nodes.values())
    assert counts["Person"] == 45
    assert counts["Team"] == 6
    assert counts["Service"] == 30
    assert counts["PR"] == 300
    assert counts["Deploy"] == 140
    assert counts["Thread"] == 150
    assert counts["Ticket"] == 80
    assert counts["Decision"] == 15
    assert counts["Incident"] == 10
    assert counts["Channel"] == 13
    contractors = [n for n in nodes.values() if n["props"].get("employment") == "contractor"]
    assert [c["id"] for c in contractors] == ["person:sam"]


def test_filler_pr_numbers_stay_in_range(nodes):
    numbers = {n["props"]["number"] for n in nodes.values() if n["label"] == "PR"}
    assert len(numbers) == 300
    assert numbers - {479, 482, 517, 518} <= set(range(180, 479))


# ---------------------------------------------------------------- referential integrity


def test_every_edge_endpoint_exists(nodes, edges):
    missing = [(e["type"], e["src"], e["dst"]) for e in edges
               if e["src"] not in nodes or e["dst"] not in nodes]  # fmt: skip
    assert missing == []


def test_node_properties_are_simple_values(nodes, edges):
    """FalkorDB properties must be numbers, strings, booleans (no maps, no None)."""
    for item in [*(n["props"] for n in nodes.values()), *(e["props"] for e in edges)]:
        for key, value in item.items():
            assert isinstance(value, str | int | float | bool), (key, value)


def test_no_node_is_an_orphan(nodes, edges):
    linked = {e["src"] for e in edges} | {e["dst"] for e in edges}
    assert set(nodes) - linked == set()


# ---------------------------------------------------------------- access information


def test_every_source_node_has_access_properties(nodes):
    for n in nodes.values():
        if n["label"] in SOURCE_LABELS:
            props = n["props"]
            for key in ("source", "team", "service", "updated_at", "access_level"):
                assert key in props, (n["id"], key)
            assert props["access_level"] in {"public", "internal", "restricted", "confidential"}
            assert isinstance(props["updated_at"], int)


def test_visible_to_exists_exactly_for_restricted_and_confidential_sources(nodes, edges):
    with_edge = {e["src"] for e in edges if e["type"] == "VISIBLE_TO"}
    gated = {i for i, n in nodes.items()
             if n["props"].get("access_level") in ("restricted", "confidential")}  # fmt: skip
    assert with_edge == gated


def test_access_levels_follow_the_channel(nodes):
    levels = {c[0]: c[2] for c in story.CHANNELS}
    for n in nodes.values():
        if n["label"] == "Thread":
            assert n["props"]["access_level"] == levels[n["props"]["channel"]]


# ---------------------------------------------------------------- the permission matrix


def test_visibility_matrix_from_the_story_bible(nodes, edges):
    expect = {  # source -> persona -> visible?
        "thread:pricing-private-0142": dict(arjun=False, dana=True, sam=False, marco=False),
        "thread:pricing-private-0150": dict(arjun=False, dana=True, sam=False, marco=False),
        "inc:INC-0326": dict(arjun=False, dana=True, sam=False, marco=False),
        "thread:sec-incidents-0007": dict(arjun=False, dana=True, sam=False, marco=False),
        "thread:hr-private-0003": dict(arjun=False, dana=False, sam=False, marco=False),
        "adr:011": dict(arjun=True, dana=True, sam=False, marco=True),
        "thread:general-0003": dict(arjun=True, dana=True, sam=True, marco=True),
    }
    for source, row in expect.items():
        for persona, visible in row.items():
            assert can_see(f"person:{persona}", source, nodes, edges) is visible, (source, persona)


def test_nobody_can_see_hr_private_unless_they_hold_the_hr_role(nodes, edges):
    hr_holders = {s for s, d in edge_set(edges, "HAS_ROLE") if d == "role:hr"}
    people = [i for i, n in nodes.items() if n["label"] == "Person"]
    for tid, n in nodes.items():
        if n["label"] == "Thread" and n["props"]["channel"] == "hr-private":
            viewers = {p for p in people if can_see(p, tid, nodes, edges)}
            assert viewers == hr_holders
    assert hr_holders == set()  # no demo persona (and nobody else) has the role


def test_pricing_private_is_seen_by_the_channel_and_incident_commanders_only(nodes, edges):
    people = [i for i, n in nodes.items() if n["label"] == "Person"]
    seers = {p for p in people if can_see(p, "thread:pricing-private-0142", nodes, edges)}
    commanders = {s for s, d in edge_set(edges, "HAS_ROLE") if d == "role:incident-commander"}
    members = {f"person:{p}" for p in story.PRICING_PRIVATE_MEMBERS}
    assert seers == commanders | members
    assert "person:marco" not in seers


def test_marco_moved_from_pricing_to_data(edges):
    member_of = edge_set(edges, "MEMBER_OF")
    assert ("person:marco", "team:pricing") not in member_of
    assert ("person:marco", "team:data") in member_of
    assert ("person:marco", "team:pricing") in edge_set(edges, "WAS_MEMBER_OF")
    was = next(e for e in edges if e["type"] == "WAS_MEMBER_OF")
    assert was["props"]["to"] == story.ist("2026-08-01 00:00")
    assert ("person:marco", "channel:pricing-private") not in edge_set(edges, "IN_CHANNEL")
    assert ("person:marco", "channel:pricing-private") in edge_set(edges, "WAS_IN_CHANNEL")


def test_sam_has_no_team(edges):
    assert not [e for e in edges if e["type"] == "MEMBER_OF" and e["src"] == "person:sam"]
    assert ("person:sam", "role:contractor") in edge_set(edges, "HAS_ROLE")


def test_persona_channels_match_the_bible(edges):
    in_channel = edge_set(edges, "IN_CHANNEL")
    for persona, channels in story.PERSONA_CHANNELS.items():
        got = {d for s, d in in_channel if s == f"person:{persona}"}
        assert got == {f"channel:{c}" for c in channels}


# ---------------------------------------------------------------- planted stories


def test_story_a_evidence_path_exists(edges):
    assert ("alert:A-3001", "svc:checkout") in edge_set(edges, "FIRED_ON")
    depends = edge_set(edges, "DEPENDS_ON")
    assert ("svc:checkout", "svc:promo-engine") in depends
    assert ("svc:promo-engine", "svc:pricing") in depends
    assert ("deploy:991", "svc:pricing") in edge_set(edges, "DEPLOYED_TO")
    assert ("deploy:991", "pr:482") in edge_set(edges, "INCLUDES")


def test_story_a_red_herring_is_copy_only(nodes, edges):
    assert ("deploy:990", "svc:checkout") in edge_set(edges, "DEPLOYED_TO")
    assert ("deploy:990", "pr:479") in edge_set(edges, "INCLUDES")
    modified = {d for s, d in edge_set(edges, "MODIFIES") if s == "pr:479"}
    assert modified == {"mod:checkout/i18n/en.json"}
    assert nodes["alert:A-3001"]["props"]["started_at"] == story.ist("2026-10-14 03:00")
    assert nodes["deploy:990"]["props"]["at"] == story.ist("2026-10-14 02:48")


def test_pr_482_changes_the_ttl_from_300_to_5(edges):
    mod = next(e for e in edges if e["type"] == "MODIFIES" and e["src"] == "pr:482")
    assert mod["dst"] == "mod:pricing/config.yaml"
    assert (mod["props"]["old"], mod["props"]["new"]) == (300, 5)
    assert ("pr:482", "ticket:PRC-311") in edge_set(edges, "FIXES")
    assert ("person:priya", "pr:482") in edge_set(edges, "AUTHORED")
    assert ("person:wei", "pr:482") in edge_set(edges, "REVIEWED")
    assert ("pr:482", "repo:pricing") in edge_set(edges, "IN_REPO")


def test_decision_trail_for_the_pricing_cache(nodes, edges):
    assert ("adr:011", "wiki:pricing-cache") in edge_set(edges, "SUPERSEDES")
    assert ("adr:011", "thread:pricing-private-0142") in edge_set(edges, "DISCUSSED_IN")
    assert ("inc:INC-0307", "pr:211") in edge_set(edges, "CAUSED_BY")
    assert ("inc:INC-0307", "person:marco") in edge_set(edges, "RESOLVED_BY")
    assert {d for s, d in edge_set(edges, "AFFECTED") if s == "inc:INC-0307"} == {
        "svc:pricing", "svc:checkout"
    }  # fmt: skip
    assert ("inc:INC-0307", "pm:INC-0307") in edge_set(edges, "RECORDED_IN")
    assert nodes["inc:INC-0307"]["props"]["severity"] == "P1"
    assert nodes["adr:011"]["props"]["updated_at"] < nodes["inc:INC-0307"]["props"]["started_at"]
    assert (
        nodes["wiki:pricing-cache"]["props"]["updated_at"] < nodes["adr:011"]["props"]["updated_at"]
    )


def test_security_incident_is_confidential(nodes, edges):
    assert nodes["inc:INC-0326"]["props"]["access_level"] == "confidential"
    assert ("inc:INC-0326", "role:security") in edge_set(edges, "VISIBLE_TO")
    assert ("thread:sec-incidents-0007", "role:security") in edge_set(edges, "VISIBLE_TO")
    assert ("inc:INC-0326", "thread:sec-incidents-0007") in edge_set(edges, "DISCUSSED_IN")


def test_story_b_path(edges):
    assert ("alert:A-3002", "svc:dispatch") in edge_set(edges, "FIRED_ON")
    assert ("svc:dispatch", "svc:eta-predictor") in edge_set(edges, "DEPENDS_ON")
    assert ("deploy:1034", "svc:eta-predictor") in edge_set(edges, "DEPLOYED_TO")
    assert ("deploy:1034", "pr:517") in edge_set(edges, "INCLUDES")
    assert ("pr:517", "mod:eta-predictor/config.yaml") in edge_set(edges, "MODIFIES")
    assert ("deploy:1035", "svc:notifications") in edge_set(edges, "DEPLOYED_TO")


def test_marco_authors_at_least_25_pricing_prs_before_august(nodes, edges):
    authored = {d for s, d in edge_set(edges, "AUTHORED") if s == "person:marco"}
    before = [p for p in authored if nodes[p]["label"] == "PR"
              and nodes[p]["props"]["service"] == "pricing"
              and nodes[p]["props"]["merged_at"] < story.MARCO_MOVE]  # fmt: skip
    assert len(before) >= 25


def test_marco_is_the_top_pricing_expert(nodes, edges):
    """Plan section 9 formula: 3 per authored PR, 1 per review, 5 per resolved incident."""
    pricing_prs = {i for i, n in nodes.items() if n["label"] == "PR"
                   and n["props"]["service"] == "pricing"}  # fmt: skip
    score: Counter = Counter()
    for e in edges:
        if e["dst"] in pricing_prs and e["type"] in ("AUTHORED", "REVIEWED"):
            score[e["src"]] += 3 if e["type"] == "AUTHORED" else 1
    resolved_pricing = {s for s, d in edge_set(edges, "AFFECTED") if d == "svc:pricing"}
    for s, d in edge_set(edges, "RESOLVED_BY"):
        if s in resolved_pricing:
            score[d] += 5
    ranked = score.most_common(2)
    assert ranked[0][0] == "person:marco"
    assert ranked[0][1] > 2 * ranked[1][1]


def test_ines_authors_every_ledger_pr_and_hana_reviews_them(nodes, edges):
    ledger = {
        i for i, n in nodes.items() if n["label"] == "PR" and n["props"]["service"] == "ledger"
    }
    assert len(ledger) >= 10
    authors = {s for s, d in edge_set(edges, "AUTHORED") if d in ledger}
    reviewers = {s for s, d in edge_set(edges, "REVIEWED") if d in ledger}
    assert authors == {"person:ines"} and reviewers == {"person:hana"}
    # nobody else touches ledger code in any way
    ledger_mods = {i for i, n in nodes.items() if n["label"] == "CodeModule"
                   and n["props"]["path"].startswith("ledger/")}  # fmt: skip
    touching = {s for s, d in edge_set(edges, "MODIFIES") if d in ledger_mods}
    assert touching == ledger


def test_services_match_the_bible(nodes, edges):
    assert len(story.SERVICES) == 30
    depends = edge_set(edges, "DEPENDS_ON")
    assert len(depends) == sum(len(d) for *_, d in story.SERVICES)
    assert all(e["props"] == {"w": 1} for e in edges if e["type"] == "DEPENDS_ON")
    assert nodes["svc:pricing"]["props"]["tier"] == 1
    assert ("team:pricing", "svc:pricing") in edge_set(edges, "OWNS")
    for name, *_ in story.SERVICES:
        assert f"mod:{name}/config.yaml" in nodes
        mods = [n for n in nodes.values() if n["label"] == "CodeModule"
                and n["props"]["path"].startswith(f"{name}/")]  # fmt: skip
        assert 2 <= len(mods) <= 4


def test_planted_facts_survive_in_the_text(nodes):
    for id_, planted in story.PLANTED_TEXT.items():
        props = nodes[id_]["props"]
        blob = (props["title"] + " " + props["text"]).lower()
        for fact in planted["required"]:
            assert fact.lower() in blob, (id_, fact)


def test_rewritten_text_without_required_facts_falls_back_to_the_template(tmp_path):
    (tmp_path / "adrs.json").write_text(json.dumps({"adr:011": {"title": "x", "text": "no facts"}}))
    b = generate.build(text_dir=tmp_path)
    assert "300s" in b.nodes["adr:011"]["props"]["text"]


def test_valid_rewritten_text_is_used(tmp_path):
    new = {"title": "Pricing cache TTL", "text": "TTL stays at 300s or higher. Vendor rate limit. "
           "This supersedes the wiki page."}  # fmt: skip
    (tmp_path / "adrs.json").write_text(json.dumps({"adr:011": new}))
    b = generate.build(text_dir=tmp_path)
    assert b.nodes["adr:011"]["props"]["text"] == new["text"]


def test_threads_mention_services_and_few_people(nodes, edges):
    mentions = [e for e in edges if e["type"] == "MENTIONS"]
    for tid, n in nodes.items():
        if n["label"] != "Thread" or n["props"]["channel"] == "hr-private":
            continue
        svcs = [e for e in mentions if e["src"] == tid and e["dst"].startswith("svc:")]
        people = [e for e in mentions if e["src"] == tid and e["dst"].startswith("person:")]
        assert 1 <= len(svcs) <= 3, tid
        assert len(people) <= 3, tid


def test_ticket_keys_use_the_team_prefix(nodes):
    for n in nodes.values():
        if n["label"] == "Ticket":
            assert n["props"]["key"].split("-")[0] == story.TICKET_PREFIX[n["props"]["team"]]
            assert n["props"]["access_level"] == "internal"


# ---------------------------------------------------------------- golden questions


def read_jsonl(name: str) -> list[dict]:
    lines = (EVAL / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_golden_has_enough_variety():
    golden = read_jsonl("golden.jsonl")
    assert len(golden) >= 50
    assert len({q["id"] for q in golden}) == len(golden)
    assert {q["type"] for q in golden} == {"lookup", "synthesis", "conflicting", "stale", "refuse"}
    assert {q["persona"] for q in golden} == set(PERSONAS)
    for q in golden:
        assert set(q) == {"id", "type", "persona", "question", "expected_sources",
                          "must_include", "must_not_include_ids", "should_refuse"}  # fmt: skip
        assert q["should_refuse"] == (q["type"] == "refuse")


def test_golden_ids_exist_and_respect_permissions(nodes, edges):
    for q in read_jsonl("golden.jsonl"):
        person = f"person:{q['persona']}"
        for i in q["expected_sources"] + q["must_not_include_ids"]:
            assert i in nodes, (q["id"], i)
        for i in q["expected_sources"]:
            if (
                "access_level" in nodes[i]["props"]
            ):  # answerable questions only cite visible sources
                assert can_see(person, i, nodes, edges), (q["id"], i)
        for i in q["must_not_include_ids"]:
            assert not can_see(person, i, nodes, edges), (q["id"], i)


def test_investigation_scenarios_point_at_real_nodes(nodes):
    scenarios = read_jsonl("investigations.jsonl")
    assert {s["id"] for s in scenarios} == {"inv-A-arjun", "inv-A-dana", "inv-B-arjun"}
    for s in scenarios:
        assert f"alert:{s['alert_id']}" in nodes
        ids = [s["expected_root_cause"], *s["expected_rejected"], *s["evidence_path"],
               *s["must_cite"], *s["must_not_include_ids"], s["expected_page"],
               *s["expected_consult"], *s["expected_notify"]]  # fmt: skip
        assert all(i in nodes for i in ids)
