"""Find which services, people and other sources a text talks about (MENTIONS edges).

This is the "entity resolution" step of plan section 19, in its simplest form: a FIXED LIST of
known names plus ALIASES, with a CONFIDENCE score on every match. No model involved, so the
result is the same on every run and easy to explain.

    extract_entities("Priya, can you check the pricing service?")
    -> {"person:priya": 0.8, "svc:pricing": 0.9}

Confidence rules (highest match wins):
    1.0   exact id or key: `svc:pricing`, `@priya`, `ADR-011`, `INC-0307`, `PRC-311`
    0.95  PR number ("PR #482"); a person's full name; a hyphenated service name (`promo-engine`)
    0.9   "<name> service" / "<name> svc" (also with a hyphenated name written with a space)
    0.8   a person's first name (not when it is only the "Name:" label of a chat line)
    0.8   a rare one-word service name ("ledger")
    0.6   a common one-word service name ("orders", "search", "menu"...). Too ambiguous to keep
          with the default threshold of 0.75: "search" is usually just the verb.

Not implemented: matching by embedding similarity (the third idea in plan section 19).
"""

from __future__ import annotations

import re
from functools import cache

from lore.data_gen import story

DEFAULT_MIN_CONFIDENCE = 0.75
RARE_SERVICE_WORDS = {"ledger"}  # one-word names that are unlikely to be used as plain words

TICKET_KEY = re.compile(r"\b(" + "|".join(story.TICKET_PREFIX.values()) + r")-(\d+)\b")
ADR_REF = re.compile(r"\bADR-(\d{3})\b")
INC_REF = re.compile(r"\bINC-(\d{4})\b")
PR_REF = re.compile(r"\bPR\s?#(\d+)\b")
SPEAKER_LABEL = re.compile(r"^\s*\S+:\s", re.MULTILINE)  # "Priya: ..." is who talks, not a mention


@cache
def _patterns() -> list[tuple[re.Pattern, str, float]]:
    """(regex, entity id, confidence) for every known service and person."""
    out: list[tuple[re.Pattern, str, float]] = []
    for name, *_ in story.SERVICES:
        sid = f"svc:{name}"
        spaced = name.replace("-", " ")
        out.append((re.compile(rf"\b{re.escape(sid)}\b"), sid, 1.0))
        out.append((re.compile(rf"\b{re.escape(spaced)}\s+(?:service|svc)\b", re.I), sid, 0.9))
        if "-" in name:
            out.append((re.compile(rf"\b{re.escape(name)}\b", re.I), sid, 0.95))
            out.append((re.compile(rf"\b{re.escape(spaced)}\b", re.I), sid, 0.9))
        else:
            bare = 0.8 if name in RARE_SERVICE_WORDS else 0.6
            out.append((re.compile(rf"\b{re.escape(name)}\b", re.I), sid, bare))
    for slug, full_name, *_ in story.PEOPLE:
        pid = f"person:{slug}"
        first = full_name.split()[0]
        out.append((re.compile(rf"@{slug}\b", re.I), pid, 1.0))
        out.append((re.compile(rf"\b{re.escape(full_name)}\b", re.I), pid, 0.95))
        out.append((re.compile(rf"\b{re.escape(first)}\b"), pid, 0.8))  # case-sensitive: a name
    return out


def extract_entities(text: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> dict[str, float]:
    """Map entity id -> confidence for everything in `text` at or above `min_confidence`."""
    found: dict[str, float] = {}

    def keep(entity: str, conf: float) -> None:
        found[entity] = max(found.get(entity, 0.0), conf)

    for key in TICKET_KEY.finditer(text):
        keep(f"ticket:{key.group(1)}-{key.group(2)}", 1.0)
    for m in ADR_REF.finditer(text):
        keep(f"adr:{m.group(1)}", 1.0)
    for m in INC_REF.finditer(text):
        keep(f"inc:INC-{m.group(1)}", 1.0)
    for m in PR_REF.finditer(text):
        keep(f"pr:{m.group(1)}", 0.95)

    body = SPEAKER_LABEL.sub("", text)
    for pattern, entity, conf in _patterns():
        if pattern.search(body):
            keep(entity, conf)
    return {e: c for e, c in sorted(found.items()) if c >= min_confidence}
