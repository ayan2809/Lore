"""Rerank is pure Python, so every rule is checked directly."""

from __future__ import annotations

import pytest

from lore.rerank import (
    DEFAULT_WEIGHTS,
    HALF_LIFE_DAYS,
    explain,
    merge_duplicates,
    recency_score,
    rerank,
)
from lore.retrieval import Candidate

NOW = 1_800_000_000
DAY = 86_400


def cand(id_, **kw) -> Candidate:
    return Candidate(id=id_, text=kw.pop("text", f"text of {id_}"), **kw)


def test_default_weights_are_the_documented_ones():
    assert DEFAULT_WEIGHTS == {"meaning": 0.5, "keyword": 0.2, "graph": 0.2, "recency": 0.1}
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_recency_halves_every_half_life():
    assert recency_score(NOW, NOW) == pytest.approx(1.0)
    assert recency_score(NOW - int(HALF_LIFE_DAYS * DAY), NOW) == pytest.approx(0.5)
    assert recency_score(NOW - int(2 * HALF_LIFE_DAYS * DAY), NOW) == pytest.approx(0.25)
    assert recency_score(None, NOW) == 0.0
    assert recency_score(NOW + 10 * DAY, NOW) == pytest.approx(1.0)  # future dates do not exceed 1


def test_duplicates_are_merged_keeping_the_max_of_each_signal():
    found = [
        cand("adr:011", meaning=0.8, text="vector chunk", chunk_id="adr:011#1"),
        cand("adr:011", keyword=7.0, text="keyword chunk", chunk_id="adr:011#0"),
        cand("adr:011", meaning=0.6, graph=0.5, title="TTL", source="adr"),
    ]
    [merged] = merge_duplicates(found)
    assert (merged.meaning, merged.keyword, merged.graph) == (0.8, 7.0, 0.5)
    assert merged.text == "vector chunk" and merged.chunk_id == "adr:011#1"  # best meaning wins
    assert merged.title == "TTL" and merged.source == "adr"  # missing fields are filled in


def test_merge_does_not_change_the_inputs():
    original = cand("a", meaning=0.5)
    merge_duplicates([original, cand("a", meaning=0.9)])
    assert original.meaning == 0.5


def test_keyword_scores_are_normalised_by_the_best_in_the_batch():
    ranked = rerank([cand("a", keyword=8.0), cand("b", keyword=4.0)], NOW)
    by_id = {c.id: c for c in ranked}
    assert by_id["a"].keyword == 1.0 and by_id["b"].keyword == 0.5


def test_no_keyword_hits_means_zero_not_a_division_error():
    [c] = rerank([cand("a", meaning=0.5)], NOW)
    assert c.keyword == 0.0


def test_score_is_the_weighted_sum():
    c = cand("a", meaning=0.8, keyword=3.0, graph=0.5, updated_at=NOW)
    [r] = rerank([c], NOW)
    assert r.score == pytest.approx(0.5 * 0.8 + 0.2 * 1.0 + 0.2 * 0.5 + 0.1 * 1.0)
    assert "=" in explain(r) and f"{r.score:.2f}" in explain(r)


def test_results_are_sorted_best_first_with_stable_ties():
    ranked = rerank([cand("b", meaning=0.5), cand("a", meaning=0.5), cand("c", meaning=0.9)], NOW)
    assert [c.id for c in ranked] == ["c", "a", "b"]


def test_recency_breaks_a_meaning_tie_in_favour_of_the_newer_source():
    old = cand("wiki:pricing-cache", meaning=0.8, updated_at=NOW - 500 * DAY)
    new = cand("adr:011", meaning=0.8, updated_at=NOW - 30 * DAY)
    assert [c.id for c in rerank([old, new], NOW)] == ["adr:011", "wiki:pricing-cache"]


def test_custom_weights_change_the_order():
    a = cand("a", meaning=0.9)
    b = cand("b", graph=1.0)
    assert rerank([a, b], NOW)[0].id == "a"
    graph_first = {"meaning": 0.1, "keyword": 0.0, "graph": 0.9, "recency": 0.0}
    assert rerank([a, b], NOW, graph_first)[0].id == "b"


def test_rerank_is_idempotent():
    found = [cand("a", keyword=5.0, meaning=0.4), cand("b", keyword=2.0, meaning=0.9)]
    once = rerank(found, NOW)
    twice = rerank(once, NOW)
    assert [(c.id, round(c.score, 6)) for c in once] == [(c.id, round(c.score, 6)) for c in twice]


def test_empty_input():
    assert rerank([], NOW) == []
