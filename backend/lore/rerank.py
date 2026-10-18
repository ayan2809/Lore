"""Rerank: one score you can explain (plan section 8, "Ask the brain" stage 2).

    score = 0.5 * meaning + 0.2 * keyword + 0.2 * graph + 0.1 * recency

Every signal is a number between 0 and 1:
- meaning  : vector similarity of the best chunk (from retrieval.py)
- keyword  : full-text relevance, divided by the best full-text score in this batch
- graph    : closeness to the service in question (1.0 = the service itself)
- recency  : 0.5 ** (age / HALF_LIFE_DAYS), so a source loses half its recency score every
             HALF_LIFE_DAYS days. It is the smallest weight on purpose: fresh does not mean right
             (an old ADR still beats a new chat message; conflicts are settled in policy.py).

Pure Python, no database. Final weights go in DECISIONS.md after tuning on the golden questions.
"""

from __future__ import annotations

from lore.retrieval import Candidate

DEFAULT_WEIGHTS = {"meaning": 0.5, "keyword": 0.2, "graph": 0.2, "recency": 0.1}
HALF_LIFE_DAYS = 180.0  # about six months: a 6-month-old source gets recency 0.5, a year old 0.25
SECONDS_PER_DAY = 86_400


def recency_score(updated_at: int | None, now_ts: int, half_life_days: float = HALF_LIFE_DAYS):
    """1.0 for something updated just now, halving every `half_life_days`. Unknown date -> 0."""
    if updated_at is None:
        return 0.0
    age_days = max(0.0, (now_ts - updated_at) / SECONDS_PER_DAY)
    return 0.5 ** (age_days / half_life_days)


def merge_duplicates(candidates: list[Candidate]) -> list[Candidate]:
    """One entry per source id. Each signal keeps its maximum across the searches.

    The text comes from the entry with the highest meaning score (the best matching chunk);
    if no entry has a meaning score, from the first entry that has any text.
    """
    merged: dict[str, Candidate] = {}
    for c in candidates:
        current = merged.get(c.id)
        if current is None:
            merged[c.id] = c.model_copy()
            continue
        best_text_from = c if c.meaning > current.meaning else current
        for signal in ("meaning", "keyword", "graph"):
            setattr(current, signal, max(getattr(current, signal), getattr(c, signal)))
        current.text = best_text_from.text or current.text or c.text
        current.chunk_id = best_text_from.chunk_id or current.chunk_id or c.chunk_id
        current.related_ids = sorted(set(current.related_ids) | set(c.related_ids))
        for field in ("source", "title", "updated_at", "access_level", "label", "service"):
            if getattr(current, field) is None:
                setattr(current, field, getattr(c, field))
    return list(merged.values())


def rerank(
    candidates: list[Candidate], now_ts: int, weights: dict[str, float] = DEFAULT_WEIGHTS
) -> list[Candidate]:
    """Merge duplicates, normalise keyword scores, compute recency and the final score.

    Returns new Candidate objects sorted best first (ties broken by id so the order is stable).
    """
    merged = merge_duplicates(candidates)
    top_keyword = max((c.keyword for c in merged), default=0.0)
    for c in merged:
        c.keyword = c.keyword / top_keyword if top_keyword > 0 else 0.0
        c.recency = recency_score(c.updated_at, now_ts)
        c.score = sum(weights[name] * getattr(c, name) for name in weights)
    return sorted(merged, key=lambda c: (-c.score, c.id))


def explain(c: Candidate, weights: dict[str, float] = DEFAULT_WEIGHTS) -> str:
    """Human-readable score, e.g. '0.50*0.91 + 0.20*1.00 + ... = 0.87'."""
    parts = " + ".join(f"{w:.2f}*{getattr(c, name):.2f}" for name, w in weights.items())
    return f"{parts} = {c.score:.2f}"
