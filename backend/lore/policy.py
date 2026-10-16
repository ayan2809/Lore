"""Rules that must always hold, written in code instead of left to the model (plan section 4).

- severity_for         : severity from service tiers, never from the model
- SOURCE_RANK          : which kind of source wins when two disagree
- resolve_conflicts    : pick the winner and tag the others
- check_post_audience  : may this message go to this channel with these citations?
- check_request        : block clearly out-of-policy requests before any agent runs

`check_request` is deliberately simple keyword/regex matching. It is a first guard rail, not
a classifier: anything it does not recognise is allowed, and the real protection is still the
permission filter inside every Cypher query and the human approval click on every action.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lore.db import GraphLike, load_query
from lore.models import SourceRef

# ------------------------------------------------------------------ severity


def severity_for(blast_rows: list[dict[str, Any]], service_tiers: Mapping[str, int] | None = None):
    """P1 if a tier-1 service is in the failing service + its blast radius, P2 for tier 2, else P3.

    `blast_rows` are the rows from the blast_radius tool (the failing service has hops = 0). Each
    row has an `id` and usually a `tier`; `service_tiers` (service id -> tier) fills in any row
    that has no tier. No rows at all means we know nothing, so the answer is the lowest, P3.
    """
    service_tiers = service_tiers or {}
    tiers = []
    for row in blast_rows:
        tier = row.get("tier")
        if tier is None:
            tier = service_tiers.get(row.get("id", ""))
        if tier is not None:
            tiers.append(int(tier))
    if not tiers:
        return "P3"
    best = min(tiers)  # tier 1 is the most critical
    return "P1" if best <= 1 else "P2" if best == 2 else "P3"


# ------------------------------------------------------------------ conflicting sources

# Story-bible section 9: Decision (ADR) > runbook > postmortem > ticket > Slack thread > wiki.
# Keys are the `source` values used in the graph, plus the label names, so either spelling works.
# Anything not listed (for example a plain PR) ranks 0.
SOURCE_RANK: dict[str, int] = {
    "adr": 6,
    "decision": 6,
    "runbook": 5,
    "postmortem": 4,
    "incident": 4,
    "ticket": 3,
    "jira": 3,
    "slack": 2,
    "thread": 2,
    "wiki": 1,
    "doc": 1,
}


def rank_of(ref: SourceRef) -> int:
    return SOURCE_RANK.get(ref.source.lower(), 0)


def resolve_conflicts(
    sources: list[SourceRef], supersedes: set[tuple[str, str]]
) -> tuple[SourceRef | None, list[SourceRef]]:
    """Decide which of several disagreeing sources to trust.

    `supersedes` holds pairs (newer_id, older_id), like the graph's (newer)-[:SUPERSEDES]->(older).
    Order of rules:
      1. A source that another source in the list supersedes is out (SUPERSEDES always wins).
      2. Among the rest, the higher SOURCE_RANK wins.
      3. At the same rank, the newer `updated_at` wins.
    Returns (winner, losers). Losers are copies tagged `conflict=True` so the UI can show both
    sides. An empty list gives (None, []).
    """
    if not sources:
        return None, []
    ids = {s.id for s in sources}
    replaced = {old for new, old in supersedes if new in ids and old in ids}
    contenders = [s for s in sources if s.id not in replaced] or sources
    winner = max(contenders, key=lambda s: (rank_of(s), s.updated_at or 0))
    losers = [s for s in sources if s.id != winner.id]
    losers.sort(key=lambda s: (-rank_of(s), -(s.updated_at or 0), s.id))
    return winner, [s.model_copy(update={"conflict": True}) for s in losers]


# ------------------------------------------------------------------ policy decisions


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None  # why it was blocked; shown to the user


def channel_id_for(target: str) -> str:
    """'#incidents' -> 'channel:incidents'. Already-prefixed ids pass through."""
    name = target.strip().lstrip("#")
    return name if name.startswith("channel:") else f"channel:{name}"


def check_post_audience(graph: GraphLike, channel_id: str, cited_ids: list[str]) -> PolicyDecision:
    """Everyone who can read the channel must be allowed to see every cited source.

    Two read-only queries: channel_info (does it exist?) and post_audience_check (which readers
    cannot see which source?). See the comments in those .cypher files for the exact rule.
    """
    channel = channel_id_for(channel_id)
    if not graph.ro(load_query("channel_info"), {"channel": channel}).rows:
        return PolicyDecision(False, f"Unknown channel {channel_id}.")
    if not cited_ids:
        return PolicyDecision(True)
    params = {"channel": channel, "cited_ids": list(cited_ids)}
    violations = graph.ro(load_query("post_audience_check"), params).dicts()
    if not violations:
        return PolicyDecision(True)
    sources = sorted({v["source_id"] for v in violations})
    readers = sorted({v["reader_name"] or v["reader_id"] for v in violations})
    shown = ", ".join(readers[:3]) + (" and others" if len(readers) > 3 else "")
    return PolicyDecision(
        False,
        f"Blocked: {channel_id} readers ({shown}) are not allowed to see "
        f"{', '.join(sources)}. Remove those citations or post to a narrower channel.",
    )


# ------------------------------------------------------------------ request policy

_ROLLBACK = re.compile(r"\b(roll\s*back|rollback|revert)\b", re.I)
_PROD = re.compile(r"\b(prod|production)\b", re.I)
_SECURITY_WORDS = re.compile(
    r"\b(security|sec-incident|leak(ed)?|credentials?|secrets?|api[ -]?keys?|confidential|"
    r"vendor (rates|contract)|salary|hr)\b",
    re.I,
)
_POST_VERBS = re.compile(r"\b(post|send|share|publish|paste|announce|broadcast)\b", re.I)
_PUBLIC_CHANNELS = re.compile(
    r"#general\b|\bgeneral channel\b|\beveryone\b|\bpublic channel\b", re.I
)
_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)|"
    r"(reveal|show|print) (your |the )?(system )?prompt|"
    r"\b(pretend|act) (to be|as|you are)\b|you are now\b|"
    r"\b(i am|i'm|answer as|reply as|respond as|log me in as) "
    r"(the )?(admin|administrator|root|dana)\b",
    re.I,
)
_UNRELATED = re.compile(
    r"\b(weather|joke|poem|song lyrics?|recipe|horoscope|stock price|football score|"
    r"movie|translate this|write (me )?(a|an) (poem|story|essay|song))\b",
    re.I,
)


def check_request(text: str) -> PolicyDecision:
    """Block requests Lore must never act on. Keyword/regex rules, see the module docstring."""
    if _INJECTION.search(text):
        return PolicyDecision(
            False, "Blocked: Lore cannot change who you are or its own rules. Ask a question."
        )
    if _ROLLBACK.search(text) and _PROD.search(text) and not text.rstrip().endswith("?"):
        return PolicyDecision(
            False,
            "Blocked: Lore never rolls back production. It can propose a rollback "
            "for a human to review.",
        )
    if _POST_VERBS.search(text) and _PUBLIC_CHANNELS.search(text) and _SECURITY_WORDS.search(text):
        return PolicyDecision(
            False,
            "Blocked: security or confidential details must not be posted to a public channel.",
        )
    if _UNRELATED.search(text):
        return PolicyDecision(
            False, "Blocked: Lore only answers questions about Kettle's engineering and incidents."
        )
    return PolicyDecision(True)
