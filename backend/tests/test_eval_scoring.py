from eval import scoring as s


def test_recall_at_k_counts_expected_in_top_k_and_ignores_chunk_suffix():
    returned = ["adr:011#0", "pr:482", "x", "y", "z", "wiki:pricing-cache"]
    assert s.recall_at_k(returned, ["adr:011", "pr:482"]) == 1.0
    assert s.recall_at_k(returned, ["adr:011", "wiki:pricing-cache"]) == 0.5  # 6th is outside k=5
    assert s.recall_at_k(returned, []) is None


def test_forbidden_hits_normalises_chunks():
    hits = s.forbidden_hits(
        ["adr:011#1", "thread:pricing-private-0142#0"], {"thread:pricing-private-0142"}
    )
    assert hits == ["thread:pricing-private-0142"]
    assert s.forbidden_hits(["adr:011"], {"inc:INC-0326"}) == []


def test_must_include_is_case_insensitive_and_partial():
    assert s.must_include_score("The TTL is 300 seconds", ["300", "seconds"]) == 1.0
    assert s.must_include_score("The TTL is 300", ["300", "ADR-011"]) == 0.5
    assert s.must_include_score("anything", []) is None


def test_cited_ratio_requires_citations_among_seen_sources():
    claims = [
        {"text": "a", "citations": ["adr:011"]},
        {"text": "b", "citations": []},
        {"text": "c", "citations": ["adr:011", "pr:999"]},  # pr:999 was never retrieved
    ]
    assert s.cited_ratio(claims, {"adr:011"}) == 1 / 3
    assert s.cited_ratio([], {"adr:011"}) is None


def test_score_retrieval_flags_persona_forbidden_ids():
    case = {"id": "q1", "type": "easy", "persona": "sam", "expected_sources": ["svc:pricing"]}
    row = s.score_retrieval(case, ["svc:pricing", "adr:011"])
    assert row["recall"] == 1.0 and row["forbidden"] == ["adr:011"]
    dana = {"id": "q2", "type": "easy", "persona": "dana", "expected_sources": []}
    assert s.score_retrieval(dana, ["thread:pricing-private-0142"])["forbidden"] == []


def test_score_generation_refusal_and_leak():
    case = {
        "id": "q3",
        "type": "refuse",
        "persona": "sam",
        "should_refuse": True,
        "must_include": [],
        "must_not_include_ids": [],
    }
    refused = {"refused": True, "claims": [], "sources": []}
    assert s.score_generation(case, refused)["refusal_ok"] is True
    leaky = {
        "refused": False,
        "sources": [{"id": "inc:INC-0326"}],
        "claims": [{"text": "key leaked", "citations": ["inc:INC-0326"]}],
    }
    row = s.score_generation(case, leaky)
    assert row["refusal_ok"] is False and row["forbidden"] == ["inc:INC-0326"]


def test_score_investigation():
    case = {
        "id": "a",
        "expected_root_cause": "pr:482",
        "expected_rejected": ["pr:479"],
        "expected_severity": "P1",
        "expected_page": "person:rahul",
        "expected_consult": ["person:marco"],
        "expected_notify": ["person:priya"],
    }
    report = {
        "root_cause": "pr:482",
        "severity": "P1",
        "rejected_suspects": [{"text": "copy only", "citations": ["pr:479"]}],
        "people": {"page": "person:rahul", "consult": ["person:marco"], "notify": ["person:priya"]},
    }
    row = s.score_investigation(case, report, {"steps": 11, "total_ms": 9000, "cost_usd": 0.05})
    assert row["root_cause_ok"] and row["red_herring_rejected"] and row["people_ok"]
    bad = s.score_investigation(case, {"root_cause": "pr:479"}, None)
    assert not bad["root_cause_ok"] and not bad["people_ok"]
    summary = s.summarise_investigations([row, bad])
    assert summary["root_cause"] == 0.5 and summary["steps"] == 11


def test_aggregation_and_formatting():
    rows = [
        {"id": "1", "type": "a", "recall": 1.0, "forbidden": []},
        {"id": "2", "type": "a", "recall": 0.5, "forbidden": ["x"]},
        {"id": "3", "type": "b", "recall": None, "forbidden": []},
    ]
    summary = s.summarise_retrieval(rows)
    assert summary == {"cases": 3, "recall": 0.75, "forbidden": 1}
    assert s.by_type(rows, "recall") == {"a": 0.75, "b": None}
    assert s.fmt(0.75, percent=True) == "75%" and s.fmt(None) == "n/a"
    assert s.markdown_table(["a", "b"], [[1, 2]]).splitlines()[1] == "|---|---|"


def test_report_and_history_render_from_scored_rows(tmp_path):
    from eval import run

    case = {
        "id": "q1",
        "type": "easy",
        "persona": "arjun",
        "expected_sources": ["svc:pricing"],
        "must_include": ["rahul"],
        "should_refuse": False,
    }
    ok = s.score_retrieval(case, ["svc:pricing"])
    miss = s.score_retrieval(case, ["x"])
    answer = {
        "claims": [{"text": "Rahul owns it", "citations": ["svc:pricing"]}],
        "sources": [{"id": "svc:pricing"}],
    }
    gen = s.score_generation(case, answer)
    results = {
        "retrieval": {"graph": [ok], "vector": [miss]},
        "generation": {"graph": [gen], "vector": [gen]},
        "investigations": {},
        "leaks": [{"persona": "sam", "probes": 3, "leaks": []}],
    }
    meta = {
        "when": "2026-10-16 12:00",
        "modes": ["graph", "vector"],
        "layers": ["retrieval"],
        "llm": "fake",
        "n_cases": 1,
        "notes": [],
    }
    text = run.render_report(results, meta)
    assert "## Graph ON vs OFF" in text and "100%" in text and "0%" in text
    assert "retrieval/vector q1" in text  # the miss is listed under "What failed"
    history = tmp_path / "history.csv"
    run.append_history(history, results, meta)
    run.append_history(history, results, meta)
    lines = history.read_text().splitlines()
    assert lines[0].startswith("timestamp,mode") and len(lines) == 5  # header + 2 runs x 2 modes
