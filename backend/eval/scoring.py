"""Deterministic scoring for the eval harness (plan section 10). No model is used to grade.

Everything here is a pure function over plain values, so it is unit-tested without FalkorDB.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from statistics import mean
from typing import Any

# Ids each persona must NEVER see (docs/story-bible.md section 4). The leak check fails if any of
# these shows up in search results or citations. Per-question lists in golden.jsonl
# (`must_not_include_ids`) are checked in addition.
_SECURITY = {"inc:INC-0326", "thread:sec-incidents-0007"}
_PRICING_PRIVATE = {"thread:pricing-private-0142", "thread:pricing-private-0150"}
_HR = {"thread:hr-private-0003"}
FORBIDDEN_BY_PERSONA: dict[str, set[str]] = {
    "arjun": _SECURITY | _PRICING_PRIVATE | _HR,
    "dana": set(_HR),
    "sam": _SECURITY | _PRICING_PRIVATE | _HR | {"adr:011"},
    "marco": _SECURITY | _PRICING_PRIVATE | _HR,
}


def source_id(any_id: str) -> str:
    """'adr:011#0' (a chunk id) -> 'adr:011' (its source). Source ids pass through unchanged."""
    return any_id.split("#", 1)[0]


def recall_at_k(returned: list[str], expected: list[str], k: int = 5) -> float | None:
    """Share of the expected sources found in the first k results. None if nothing is expected."""
    if not expected:
        return None
    top = {source_id(i) for i in returned[:k]}
    return sum(1 for e in expected if e in top) / len(expected)


def forbidden_hits(returned: Iterable[str], forbidden: Iterable[str]) -> list[str]:
    """Which forbidden source ids appear in `returned` (chunk ids count as their source)."""
    banned = set(forbidden)
    return sorted({source_id(i) for i in returned} & banned)


def must_include_score(text: str, must_include: list[str]) -> float | None:
    """Share of the required phrases present in the answer (case-insensitive substring)."""
    if not must_include:
        return None
    lowered = text.lower()
    return sum(1 for phrase in must_include if phrase.lower() in lowered) / len(must_include)


def cited_ratio(claims: list[dict[str, Any]], allowed_ids: set[str]) -> float | None:
    """Share of claims with at least one citation, all of them among the sources the run saw."""
    if not claims:
        return None
    ok = sum(
        1
        for c in claims
        if c.get("citations") and all(source_id(x) in allowed_ids for x in c["citations"])
    )
    return ok / len(claims)


def refusal_correct(refused: bool, should_refuse: bool) -> bool:
    return refused == should_refuse


# --------------------------------------------------------------------------- per-case scoring


def score_retrieval(case: dict[str, Any], returned: list[str], k: int = 5) -> dict[str, Any]:
    forbidden = set(case.get("must_not_include_ids", [])) | FORBIDDEN_BY_PERSONA.get(
        case["persona"], set()
    )
    return {
        "id": case["id"],
        "type": case.get("type", ""),
        "recall": recall_at_k(returned, case.get("expected_sources", []), k),
        "forbidden": forbidden_hits(returned, forbidden),
    }


def score_generation(case: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    """`answer` is AskAnswer.model_dump()."""
    claims = answer.get("claims", [])
    text = " ".join(c["text"] for c in claims)
    source_ids = {source_id(s["id"]) for s in answer.get("sources", [])}
    cited = [source_id(x) for c in claims for x in c.get("citations", [])]
    forbidden = set(case.get("must_not_include_ids", [])) | FORBIDDEN_BY_PERSONA.get(
        case["persona"], set()
    )
    return {
        "id": case["id"],
        "type": case.get("type", ""),
        "must_include": must_include_score(text, case.get("must_include", [])),
        "cited": cited_ratio(claims, source_ids),
        "refusal_ok": refusal_correct(bool(answer.get("refused")), bool(case.get("should_refuse"))),
        "forbidden": forbidden_hits(cited + sorted(source_ids), forbidden),
    }


def score_investigation(
    case: dict[str, Any], report: dict[str, Any] | None, summary: dict[str, Any] | None
) -> dict[str, Any]:
    """Compare one investigation run with the expected answer in investigations.jsonl."""
    report = report or {}
    summary = summary or {}
    people = report.get("people") or {}
    rejected = {
        cited for r in report.get("rejected_suspects", []) for cited in r.get("citations", [])
    }
    expected_people = {
        "page": case.get("expected_page"),
        "consult": case.get("expected_consult", []),
        "notify": case.get("expected_notify", []),
    }
    people_ok = (
        (not expected_people["page"] or people.get("page") == expected_people["page"])
        and set(expected_people["consult"]) <= set(people.get("consult", []))
        and set(expected_people["notify"]) <= set(people.get("notify", []))
    )
    return {
        "id": case["id"],
        "root_cause_ok": report.get("root_cause") == case.get("expected_root_cause"),
        "red_herring_rejected": set(case.get("expected_rejected", [])) <= rejected,
        "severity_ok": case.get("expected_severity") in (None, report.get("severity")),
        "people_ok": people_ok,
        "steps": summary.get("steps"),
        "ms": summary.get("total_ms"),
        "cost_usd": summary.get("cost_usd"),
    }


# --------------------------------------------------------------------------- aggregation


def avg(values: Iterable[float | None]) -> float | None:
    """Mean of the values that exist; None if there are none."""
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def summarise_retrieval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(rows),
        "recall": avg(r["recall"] for r in rows),
        "forbidden": sum(len(r["forbidden"]) for r in rows),
    }


def summarise_generation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(rows),
        "must_include": avg(r["must_include"] for r in rows),
        "cited": avg(r["cited"] for r in rows),
        "refusal_ok": avg(1.0 if r["refusal_ok"] else 0.0 for r in rows),
        "forbidden": sum(len(r["forbidden"]) for r in rows),
    }


def summarise_investigations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def rate(key: str) -> float | None:
        return avg(1.0 if r[key] else 0.0 for r in rows)

    return {
        "runs": len(rows),
        "root_cause": rate("root_cause_ok"),
        "red_herring": rate("red_herring_rejected"),
        "severity": rate("severity_ok"),
        "people": rate("people_ok"),
        "steps": avg(r["steps"] for r in rows),
        "seconds": avg(None if r["ms"] is None else r["ms"] / 1000 for r in rows),
        "cost_usd": avg(r["cost_usd"] for r in rows),
    }


def by_type(rows: list[dict[str, Any]], key: str) -> dict[str, float | None]:
    """Mean of `key` per question type, e.g. recall for 'conflicting' questions."""
    groups: dict[str, list[float | None]] = defaultdict(list)
    for r in rows:
        groups[r["type"]].append(r.get(key))
    return {t: avg(v) for t, v in sorted(groups.items())}


# --------------------------------------------------------------------------- formatting


def fmt(value: float | int | None, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    if percent:
        return f"{value * 100:.0f}%"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)
