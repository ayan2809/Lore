"""Unit tests for the loader: chunking, fake embeddings, name matching, whitelists, write batches.

No FalkorDB needed: a recording graph stands in for it.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from lore.config import get_settings
from lore.db import QueryOutcome
from lore.loader import load
from lore.loader.chunk import chunk_text, make_chunks, source_text
from lore.loader.embed import embed_texts, fake_embedding
from lore.loader.entities import extract_entities


class RecordingGraph:
    """Implements GraphLike: remembers every write, returns nothing."""

    def __init__(self, fail_index_with: str | None = None):
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.timeouts: list[int | None] = []  # the timeout_ms of each write, in order
        self.fail_index_with = fail_index_with

    def write(
        self, cypher: str, params: dict[str, Any] | None = None, timeout_ms: int | None = None
    ) -> QueryOutcome:
        if self.fail_index_with and "INDEX" in cypher.upper() and "FOR (n:Person)" in cypher:
            raise RuntimeError(self.fail_index_with)
        self.writes.append((cypher, params or {}))
        self.timeouts.append(timeout_ms)
        return QueryOutcome(header=[], rows=[], ms=0.0)

    def ro(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome:
        raise AssertionError("the loader must not read")


# ---------------------------------------------------------------- chunking


def test_short_text_is_one_chunk():
    assert chunk_text("A short note.") == ["A short note."]


def test_long_text_is_split_near_500_characters():
    text = "\n".join(f"Message number {i}: " + "word " * 20 for i in range(12))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= 520 for c in chunks)
    assert " ".join(chunks).split() == text.split()  # nothing lost


def test_one_very_long_sentence_is_still_cut():
    chunks = chunk_text("word " * 400)
    assert len(chunks) >= 4 and all(len(c) <= 500 for c in chunks)


def test_chunk_ids_and_access_properties_follow_the_source():
    node = {
        "label": "Decision", "id": "adr:011",
        "props": {"title": "T", "text": "x " * 600, "source": "adr", "team": "pricing",
                  "service": "pricing", "updated_at": 5, "access_level": "internal"},
    }  # fmt: skip
    chunks = make_chunks(node)
    assert [c["id"] for c in chunks] == [f"adr:011#{i}" for i in range(len(chunks))]
    assert len(chunks) >= 2
    for c in chunks:
        assert c["src"] == "adr:011"
        assert c["props"]["access_level"] == "internal"
        assert c["props"]["team"] == "pricing"


def test_nodes_without_text_have_no_chunks():
    assert make_chunks({"label": "Service", "id": "svc:x", "props": {"name": "x"}}) == []


def test_title_is_added_once_unless_text_already_starts_with_it():
    assert source_text({"title": "Hello", "text": "World"}) == "Hello\nWorld"
    assert source_text({"title": "Hello", "text": "Hello there"}) == "Hello there"


# ---------------------------------------------------------------- fake embeddings


def test_fake_embeddings_are_deterministic_unit_vectors_of_the_right_size():
    dim = get_settings().embed_dim
    a, b = embed_texts(["pricing cache TTL", "pricing cache TTL"], fake=True)
    assert a == b
    assert len(a) == dim == 768
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-9)


def test_fake_embeddings_of_similar_texts_are_closer_than_unrelated_ones():
    def dot(u, v):
        return sum(x * y for x, y in zip(u, v, strict=True))

    base = fake_embedding("pricing cache ttl vendor rate limit", 768)
    near = fake_embedding("the pricing cache ttl and the vendor", 768)
    far = fake_embedding("buy fresh pizza tonight", 768)
    assert dot(base, near) > dot(base, far)


def test_fake_embedding_of_empty_text_is_still_a_unit_vector():
    v = fake_embedding("", 768)
    assert math.isclose(sum(x * x for x in v), 1.0)


def test_real_embeddings_need_a_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    with pytest.raises(RuntimeError):
        embed_texts(["x"], fake=False)


# ---------------------------------------------------------------- name matching


def test_ids_and_keys_match_with_full_confidence():
    found = extract_entities("See ADR-011, INC-0307, PRC-311 and svc:ledger.")
    assert found["adr:011"] == found["inc:INC-0307"] == found["ticket:PRC-311"] == 1.0
    assert found["svc:ledger"] == 1.0


def test_pr_numbers_match():
    assert extract_entities("Reverted PR #211 today")["pr:211"] == 0.95


def test_service_names_and_aliases():
    found = extract_entities("The promo engine calls the pricing service. Check eta-predictor.")
    assert found["svc:promo-engine"] == 0.9
    assert found["svc:pricing"] == 0.9
    assert found["svc:eta-predictor"] == 0.95


def test_common_words_are_not_services_at_the_default_threshold():
    assert extract_entities("Can you search the menu for orders?") == {}
    low = extract_entities("Can you search the menu for orders?", min_confidence=0.5)
    assert {"svc:search", "svc:menu", "svc:orders"} <= set(low)


def test_people_by_full_name_first_name_and_handle():
    found = extract_entities("Marco Bianchi wrote it. Ask Priya or @wei.")
    assert found["person:marco"] == 0.95
    assert found["person:priya"] == 0.8
    assert found["person:wei"] == 1.0


def test_speaker_labels_are_not_mentions():
    text = "Rahul: Priya, can you check the pricing service?\nPriya: yes."
    found = extract_entities(text)
    assert "person:rahul" not in found
    assert found["person:priya"] == 0.8


def test_unknown_names_are_ignored():
    assert extract_entities("Zaphod called Ford about the toaster.") == {}


# ---------------------------------------------------------------- whitelist and writes


def test_label_and_type_whitelists():
    assert load.check_label("Person") == "Person"
    assert load.check_type("MENTIONS") == "MENTIONS"
    for bad in ("Person) DETACH DELETE n //", "Nope", "person", ""):
        with pytest.raises(ValueError):
            load.check_label(bad)
    with pytest.raises(ValueError):
        load.check_type("KNOWS]->(x) DELETE x //")


def test_unknown_label_is_rejected_before_any_write():
    graph = RecordingGraph()
    bad = [{"label": "Person", "id": "person:a", "props": {}},
           {"label": "Evil) DETACH DELETE n //", "id": "x:1", "props": {}}]  # fmt: skip
    with pytest.raises(ValueError):
        load.load_nodes(graph, bad)
    assert graph.writes == []


def test_unknown_edge_type_is_rejected_before_any_write():
    graph = RecordingGraph()
    edges = [{"type": "LOVES", "src": "a", "dst": "b", "props": {}}]
    with pytest.raises(ValueError):
        load.load_edges(graph, edges, {"a": "Person", "b": "Person"})
    assert graph.writes == []


def test_nodes_are_written_in_batches_with_merge_and_parameters():
    graph = RecordingGraph()
    nodes = [{"label": "Service", "id": f"svc:{i}", "props": {"name": str(i)}} for i in range(5)]
    counts = load.load_nodes(graph, nodes, batch_size=2)
    assert counts == {"Service": 5}
    assert len(graph.writes) == 3
    cypher, params = graph.writes[0]
    assert "MERGE (n:Service {id: row.id})" in cypher and "SET n += row.props" in cypher
    assert "svc:0" not in cypher  # data travels as parameters, never in the query text
    assert [r["id"] for r in params["rows"]] == ["svc:0", "svc:1"]


def test_edges_are_merged_after_matching_both_ends_by_label():
    graph = RecordingGraph()
    edges = [{"type": "DEPENDS_ON", "src": "svc:a", "dst": "svc:b", "props": {"w": 1}}]
    load.load_edges(graph, edges, {"svc:a": "Service", "svc:b": "Service"})
    cypher, params = graph.writes[0]
    assert "MATCH (a:Service {id: row.src}) MATCH (b:Service {id: row.dst})" in cypher
    assert "MERGE (a)-[r:DEPENDS_ON]->(b)" in cypher
    assert params["rows"][0]["props"] == {"w": 1}


def test_index_statements_use_the_configured_dimension():
    statements = load.index_statements(embed_dim=384)
    vector = [s for s in statements if "VECTOR" in s]
    assert len(vector) == 2 and all("dimension: 384" in s for s in vector)
    assert all(not s.startswith("//") for s in statements)
    assert any("db.idx.fulltext.createNodeIndex('Thread'" in s for s in statements)


def test_existing_indexes_are_skipped_but_other_errors_surface():
    graph = RecordingGraph(fail_index_with="Attribute 'id' is already indexed")
    created, skipped = load.create_indexes(graph, 768)
    assert skipped == 1 and created > 20
    with pytest.raises(RuntimeError):
        load.create_indexes(RecordingGraph(fail_index_with="connection lost"), 768)


def test_full_load_runs_offline_and_is_made_of_merges():
    graph = RecordingGraph()
    stats = load.load_all(graph, fake_embeddings=True, log=lambda *_: None)
    assert stats["nodes"]["PR"] == 300
    assert stats["chunks"] > 500
    queries = [c for c, _ in graph.writes if not c.startswith(("CREATE", "CALL"))]
    assert queries and all("MERGE" in q for q in queries)
    chunk_rows = [p["rows"] for c, p in graph.writes if "MERGE (c:Chunk" in c]
    first = chunk_rows[0][0]
    assert first["props"]["access_level"] and len(first["embedding"]) == 768


def test_bulk_writes_carry_a_30_second_timeout():
    graph = RecordingGraph()
    load.load_all(graph, fake_embeddings=True, log=lambda *_: None)
    bulk = [t for (c, _), t in zip(graph.writes, graph.timeouts, strict=True) if "UNWIND" in c]
    assert bulk and set(bulk) == {30_000}


def test_extracted_mentions_never_duplicate_explicit_ones():
    nodes, edges = load.read_data()
    explicit = {(e["src"], e["dst"]) for e in edges if e["type"] == "MENTIONS"}
    extracted = load.extract_mention_edges(nodes, edges, 0.75)
    assert extracted
    assert not {(e["src"], e["dst"]) for e in extracted} & explicit
