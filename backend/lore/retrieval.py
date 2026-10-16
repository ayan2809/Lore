"""Hybrid retrieval: three ways to find sources, all permission-filtered inside Cypher.

1. `vector_search`        by meaning       (vector_search_permitted.cypher)
2. `fulltext_search`      by exact words   (fulltext_search_permitted.cypher)
3. `graph_scoped_search`  by meaning, but only sources about services near a given service
                          (graph_scoped_search.cypher)

Each returns `Candidate`s with ONE signal filled in (meaning, keyword or graph). `rerank.py`
merges the three lists and computes the final score. The viewer filter lives in the Cypher files,
so a source the viewer may not see never reaches this module.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from lore.tools import ToolContext, run_query

FETCH_K = 100  # how many chunks the vector index returns BEFORE the permission filter
RESTRICTED_MAX_DISTANCE = 0.5  # a chunk this close in meaning counts as a "match" (tune Day 1)

_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "why",
    "what",
    "who",
    "how",
    "when",
    "which",
    "do",
    "does",
    "did",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "it",
    "this",
    "that",
    "be",
}


class Candidate(BaseModel):
    """One source that might answer the question, with the signals the reranker combines."""

    id: str  # the SOURCE id, e.g. "adr:011" (not the chunk id)
    source: str | None = None  # "slack" | "github" | "jira" | "adr" | "wiki" | ...
    title: str | None = None
    text: str = ""  # text of the best matching chunk
    updated_at: int | None = None
    access_level: str | None = None
    label: str | None = None  # graph label: "Decision", "Thread", ...
    service: str | None = None
    chunk_id: str | None = None
    # the four signals, each meant to end up in [0, 1]
    meaning: float = 0.0
    keyword: float = 0.0  # raw full-text score until rerank() normalises it
    graph: float = 0.0
    recency: float = 0.0
    score: float = 0.0  # final score, set by rerank()


def distance_to_similarity(distance: float) -> float:
    """Turn FalkorDB's vector `score` into a similarity in [0, 1] (1 = identical).

    ASSUMPTION TO VERIFY ON DAY 1 (plan L.11): with a cosine index, `score` is a DISTANCE, so
    lower = closer. We map it with 1 - distance. If the live graph shows that higher = closer,
    this is the only function to change (plus the ORDER BY in the vector .cypher files).
    """
    return max(0.0, min(1.0, 1.0 - float(distance)))


def clean_fulltext(text: str, max_terms: int = 8) -> str:
    """Make free text safe for the full-text index: words only, OR-ed together.

    "Why is ADR-011 set to 300s?" becomes "ADR | 011 | set | 300s". Punctuation such as '-' has a
    special meaning in the index query language, so we drop it.
    """
    words = re.findall(r"[A-Za-z0-9]+", text)
    terms = [w for w in words if w.lower() not in _STOPWORDS]
    return " | ".join(terms[:max_terms])


def _from_row(row: dict, **signals: float) -> Candidate:
    return Candidate(
        id=row["id"],
        source=row.get("source"),
        title=row.get("title"),
        text=row.get("text") or "",
        updated_at=row.get("updated_at"),
        access_level=row.get("access_level"),
        label=row.get("label"),
        service=row.get("service"),
        chunk_id=row.get("chunk_id"),
        **signals,
    )


def _run(ctx: ToolContext, name: str, params: dict, outcomes: list | None):
    """run_query, plus keep the QueryOutcome so a tool can show the Cypher and timing."""
    out = run_query(ctx, name, params)
    if outcomes is not None:
        outcomes.append(out)
    return out


def vector_search(
    ctx: ToolContext, qvec: list[float], k: int = 10, *, outcomes: list | None = None
) -> list[Candidate]:
    out = _run(ctx, "vector_search_permitted", {"qvec": qvec, "fetch_k": FETCH_K, "k": k}, outcomes)
    return [_from_row(r, meaning=distance_to_similarity(r["score"])) for r in out.dicts()]


def fulltext_search(
    ctx: ToolContext, text: str, k: int = 10, *, outcomes: list | None = None
) -> list[Candidate]:
    query = clean_fulltext(text)
    if not query:
        return []
    out = _run(ctx, "fulltext_search_permitted", {"text": query, "k": k}, outcomes)
    return [_from_row(r, keyword=float(r["score"])) for r in out.dicts()]  # raw; rerank normalises


def graph_scoped_search(
    ctx: ToolContext, service: str, qvec: list[float], k: int = 10, *, outcomes: list | None = None
) -> list[Candidate]:
    params = {"service": service, "qvec": qvec, "fetch_k": FETCH_K, "k": k}
    out = _run(ctx, "graph_scoped_search", params, outcomes)
    found = []
    for r in out.dicts():
        # Graph closeness: 1.0 for the service itself, 0.5 one hop away, 0.33 two hops away.
        closeness = 1.0 / (1 + (r.get("hops") or 0))
        found.append(_from_row(r, meaning=distance_to_similarity(r["score"]), graph=closeness))
    return found


def restricted_match_count(
    ctx: ToolContext, qvec: list[float], k: int = FETCH_K, *, outcomes: list | None = None
) -> tuple[int, str | None]:
    """How many relevant sources exist that the viewer may NOT see, plus who to ask.

    Returns (count, hint) such as (1, "ask the Pricing team (Rahul Verma)"). No content is read.
    The hint names the team with the most hidden matches.
    """
    params = {"qvec": qvec, "fetch_k": k, "max_distance": RESTRICTED_MAX_DISTANCE}
    rows = _run(ctx, "restricted_match_count", params, outcomes).dicts()
    if not rows:
        return 0, None
    total = sum(r["matches"] for r in rows)
    top = rows[0]  # the query orders by matches, largest first
    team = top.get("team_name") or top.get("team")
    if not team:
        return total, None
    team = team[:1].upper() + team[1:]
    lead = f" ({top['lead']})" if top.get("lead") else ""
    return total, f"ask the {team} team{lead}"
