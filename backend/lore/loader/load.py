"""Load backend/data/*.json into FalkorDB.

    uv run python -m lore.loader.load [--graph org_kettle] [--reset] [--fake-embeddings]

Steps (each one is safe to repeat, because everything is MERGE):
  1. create indexes (indexes.cypher; "already exists" errors are skipped)
  2. nodes: one `UNWIND ... MERGE` write per label per batch
  3. edges: one write per (relationship type, source label, target label) per batch.
     Nodes are merged BEFORE edges: MERGE on a whole pattern would duplicate the nodes.
  4. chunks: split source text, embed it, MERGE the Chunk nodes and `PART_OF` edges
  5. extracted MENTIONS: names found in the text (entities.py); explicit ones from edges.json win

Labels and relationship types cannot be Cypher parameters, so they are pasted into the query
text. That is only done for names on the whitelists below.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from lore.config import get_settings
from lore.db import GraphLike
from lore.loader.chunk import SOURCE_LABELS, make_chunks, source_text
from lore.loader.embed import embed_texts
from lore.loader.entities import DEFAULT_MIN_CONFIDENCE, extract_entities

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INDEX_FILE = Path(__file__).with_name("indexes.cypher")

LABELS = frozenset({
    "Person", "Team", "Role", "Channel", "Service", "Repo", "CodeModule", "PR", "Deploy",
    "Ticket", "Thread", "Doc", "Decision", "Incident", "Alert", "Chunk",
})  # fmt: skip
REL_TYPES = frozenset({
    "MEMBER_OF", "WAS_MEMBER_OF", "OWNS", "HAS_ROLE", "IN_CHANNEL", "WAS_IN_CHANNEL",
    "VISIBLE_TO", "DEPENDS_ON", "BUILT_FROM", "CONTAINS", "AUTHORED", "REVIEWED", "MODIFIES",
    "IN_REPO", "DEPLOYED_TO", "INCLUDES", "FIXES", "MENTIONS", "POSTED_IN", "IMPLEMENTS",
    "DISCUSSED_IN", "RECORDED_IN", "SUPERSEDES", "FIRED_ON", "AFFECTED", "CAUSED_BY",
    "RESOLVED_BY", "PART_OF",
})  # fmt: skip
# MENTIONS found in text may point at these kinds of node
MENTION_TARGETS = frozenset({"Service", "Person", "Decision", "Incident", "PR", "Ticket"})


def check_label(label: str) -> str:
    if label not in LABELS:
        raise ValueError(f"label {label!r} is not on the whitelist")
    return label


def check_type(rel_type: str) -> str:
    if rel_type not in REL_TYPES:
        raise ValueError(f"relationship type {rel_type!r} is not on the whitelist")
    return rel_type


def batches(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def read_data(data_dir: Path = DATA_DIR) -> tuple[list[dict], list[dict]]:
    nodes = json.loads((data_dir / "nodes.json").read_text(encoding="utf-8"))
    edges = json.loads((data_dir / "edges.json").read_text(encoding="utf-8"))
    return nodes, edges


# ---------------------------------------------------------------- indexes


def index_statements(embed_dim: int) -> list[str]:
    """Statements from indexes.cypher, comments removed, vector dimension set to embed_dim."""
    lines = [ln for ln in INDEX_FILE.read_text().splitlines() if not ln.strip().startswith("//")]
    statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    return [re.sub(r"dimension:\s*\d+", f"dimension: {embed_dim}", s) for s in statements]


def create_indexes(graph: GraphLike, embed_dim: int) -> tuple[int, int]:
    """Run every index statement. Returns (created, skipped because they already existed)."""
    created = skipped = 0
    for statement in index_statements(embed_dim):
        try:
            graph.write(statement)
            created += 1
        except Exception as exc:  # FalkorDB raises when the index is already there
            if "already" not in str(exc).lower():
                raise
            skipped += 1
    return created, skipped


# ---------------------------------------------------------------- nodes and edges


def load_nodes(graph: GraphLike, nodes: list[dict], batch_size: int = 200) -> dict[str, int]:
    by_label: dict[str, list[dict]] = {}
    for n in nodes:
        by_label.setdefault(check_label(n["label"]), []).append(
            {"id": n["id"], "props": n["props"]}
        )
    for label, rows in sorted(by_label.items()):
        query = f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row.props"
        for batch in batches(rows, batch_size):
            graph.write(query, {"rows": batch})
    return {label: len(rows) for label, rows in by_label.items()}


def load_edges(
    graph: GraphLike, edges: list[dict], label_of: dict[str, str], batch_size: int = 500
) -> dict[str, int]:
    """MERGE relationships. `label_of` maps node id -> label so MATCH can use the id index."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for e in edges:
        key = (check_type(e["type"]), label_of[e["src"]], label_of[e["dst"]])
        groups.setdefault(key, []).append(e)
    counts: dict[str, int] = {}
    for (rel_type, src_label, dst_label), rows in sorted(groups.items()):
        check_label(src_label)
        check_label(dst_label)
        query = (
            "UNWIND $rows AS row "
            f"MATCH (a:{src_label} {{id: row.src}}) MATCH (b:{dst_label} {{id: row.dst}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) SET r += row.props"
        )
        for batch in batches(rows, batch_size):
            graph.write(
                query, {"rows": [{k: e[k] for k in ("src", "dst", "props")} for e in batch]}
            )
        counts[rel_type] = counts.get(rel_type, 0) + len(rows)
    return counts


# ---------------------------------------------------------------- chunks


def load_chunks(
    graph: GraphLike, nodes: list[dict], *, fake: bool, embed_dim: int, batch_size: int = 50
) -> int:
    chunks = [c for n in nodes for c in make_chunks(n)]
    vectors = embed_texts([c["props"]["text"] for c in chunks], fake=fake)
    if vectors and len(vectors[0]) != embed_dim:
        raise ValueError(f"embedding has {len(vectors[0])} numbers, index expects {embed_dim}")
    chunk_query = (
        "UNWIND $rows AS row MERGE (c:Chunk {id: row.id}) "
        "SET c += row.props, c.embedding = vecf32(row.embedding)"
    )
    rows = [
        {"id": c["id"], "props": c["props"], "embedding": v}
        for c, v in zip(chunks, vectors, strict=True)
    ]
    for batch in batches(rows, batch_size):
        graph.write(chunk_query, {"rows": batch})
    by_label: dict[str, list[dict]] = {}
    for c in chunks:
        by_label.setdefault(check_label(c["src_label"]), []).append(
            {"id": c["id"], "src": c["src"]}
        )
    for label, part_rows in sorted(by_label.items()):
        query = (
            "UNWIND $rows AS row MATCH (c:Chunk {id: row.id}) "
            f"MATCH (s:{label} {{id: row.src}}) MERGE (c)-[:PART_OF]->(s)"
        )
        for batch in batches(part_rows, 500):
            graph.write(query, {"rows": batch})
    return len(chunks)


# ---------------------------------------------------------------- extracted MENTIONS


def extract_mention_edges(
    nodes: list[dict], edges: list[dict], min_confidence: float
) -> list[dict]:
    """MENTIONS found by alias matching, minus the ones edges.json already has (explicit wins)."""
    label_of = {n["id"]: n["label"] for n in nodes}
    explicit = {(e["src"], e["dst"]) for e in edges if e["type"] == "MENTIONS"}
    found = []
    for n in nodes:
        if n["label"] not in SOURCE_LABELS:
            continue
        for target, conf in extract_entities(source_text(n["props"]), min_confidence).items():
            if target == n["id"] or (n["id"], target) in explicit:
                continue
            if label_of.get(target) in MENTION_TARGETS:
                props = {"confidence": conf, "method": "alias"}
                found.append({"type": "MENTIONS", "src": n["id"], "dst": target, "props": props})
    return found


# ---------------------------------------------------------------- whole run


def load_all(
    graph: GraphLike,
    data_dir: Path = DATA_DIR,
    *,
    fake_embeddings: bool,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    embed_dim: int | None = None,
    log: Any = print,
) -> dict[str, Any]:
    embed_dim = embed_dim or get_settings().embed_dim
    nodes, edges = read_data(data_dir)
    label_of = {n["id"]: n["label"] for n in nodes}
    stats: dict[str, Any] = {}
    stats["indexes"] = create_indexes(graph, embed_dim)
    log(f"indexes: {stats['indexes'][0]} created, {stats['indexes'][1]} already there")
    stats["nodes"] = load_nodes(graph, nodes)
    log(f"nodes: {sum(stats['nodes'].values())}")
    stats["edges"] = load_edges(graph, edges, label_of)
    log(f"edges: {sum(stats['edges'].values())}")
    stats["chunks"] = load_chunks(graph, nodes, fake=fake_embeddings, embed_dim=embed_dim)
    log(f"chunks: {stats['chunks']} ({'FAKE' if fake_embeddings else 'Gemini'} embeddings)")
    mentions = extract_mention_edges(nodes, edges, min_confidence)
    stats["extracted_mentions"] = len(mentions)
    load_edges(graph, mentions, label_of)
    log(f"extracted MENTIONS: {len(mentions)} new (confidence >= {min_confidence})")
    return stats


def sanity_report(graph: GraphLike) -> None:
    """Print counts and an orphan check; suggest a connectivity (WCC) query to run by hand."""
    labels = graph.ro("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS c ORDER BY label")
    print("nodes by label:", {row[0]: row[1] for row in labels.rows})
    rels = graph.ro("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY t")
    print("edges by type: ", {row[0]: row[1] for row in rels.rows})
    orphans = graph.ro("MATCH (n) WHERE NOT (n)--() RETURN labels(n)[0] AS label, count(n) AS c")
    print("nodes with no edges (expect none):", {row[0]: row[1] for row in orphans.rows} or "none")
    print(
        "Next, check the graph is one connected piece (look for a single large componentId):\n"
        "  CALL algo.WCC(null) YIELD node, componentId\n"
        "  RETURN componentId, count(node) AS size ORDER BY size DESC"
    )


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Load the Kettle data into FalkorDB")
    parser.add_argument("--graph", default=settings.graph_name, help="graph (tenant) name")
    parser.add_argument("--reset", action="store_true", help="delete the graph first")
    parser.add_argument(
        "--fake-embeddings",
        action="store_true",
        default=settings.fake_embeddings,  # LORE_FAKE_EMBEDDINGS=true also turns it on
        help="offline fake vectors (then run the API with LORE_FAKE_EMBEDDINGS=true too)",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    args = parser.parse_args(argv)

    if not args.fake_embeddings and not settings.gemini_api_key:
        print("No Gemini key (LORE_GEMINI_API_KEY). Add --fake-embeddings to load without one.",
              file=sys.stderr)  # fmt: skip
        return 1

    from lore.db import GraphClient

    graph = GraphClient(settings, graph_name=args.graph)
    if args.reset:
        graph.delete_graph()
        print(f"deleted graph {args.graph}")
    load_all(graph, args.data_dir, fake_embeddings=args.fake_embeddings,
             min_confidence=args.min_confidence)  # fmt: skip
    sanity_report(graph)
    return 0


if __name__ == "__main__":
    sys.exit(main())
