"""Citation validator (plan section 8, "Answers come in a fixed, checked format").

A claim is valid only if it has at least one citation and every cited id was returned by a tool
during this run (`ToolContext.seen_ids`). Tools only ever return ids the viewer may see, so a
valid citation is also a permitted one. This is the second line of defence after the Cypher filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lore.models import Claim


@dataclass
class ValidationOutcome:
    valid: list[Claim] = field(default_factory=list)
    invalid: list[Claim] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # fed back to the model on the one retry

    @property
    def cited_ratio(self) -> float:
        total = len(self.valid) + len(self.invalid)
        return 1.0 if total == 0 else len(self.valid) / total


def validate_claims(claims: list[Claim], seen_ids: set[str]) -> ValidationOutcome:
    out = ValidationOutcome()
    for i, claim in enumerate(claims):
        if not claim.citations:
            out.invalid.append(claim)
            out.problems.append(f"claim {i} has no citations: {claim.text[:80]!r}")
            continue
        unknown = [c for c in claim.citations if c not in seen_ids]
        if unknown:
            out.invalid.append(claim)
            out.problems.append(f"claim {i} cites ids no tool returned this run: {unknown}")
            continue
        out.valid.append(claim)
    return out
