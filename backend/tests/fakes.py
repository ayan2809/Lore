"""Test doubles shared by the unit tests: a fake graph that needs no FalkorDB."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lore.db import QueryOutcome

Canned = QueryOutcome | Callable[[str, dict[str, Any]], QueryOutcome]


def outcome(header: list[str], *rows: list[Any]) -> QueryOutcome:
    """Build a canned result: outcome(["id", "name"], ["svc:pricing", "pricing"])."""
    return QueryOutcome(header=header, rows=[list(r) for r in rows], ms=1.0, server_ms=0.5)


class FakeGraph:
    """Implements `GraphLike`. Returns canned results and records every call.

    `canned` maps a SUBSTRING of the Cypher text to a QueryOutcome. Each query file starts with
    a comment like `// find_entity: ...`, so the key "find_entity:" picks that file. A query that
    matches nothing returns an empty result. Writes are never allowed: tools must be read-only.
    """

    def __init__(self, canned: dict[str, Canned] | None = None):
        self.canned = dict(canned or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []  # (cypher, params) in call order

    def on(self, key: str, result: Canned) -> FakeGraph:
        self.canned[key] = result
        return self

    def ro(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome:
        params = params or {}
        self.calls.append((cypher, params))
        for key, result in self.canned.items():
            if key in cypher:
                out = result(cypher, params) if callable(result) else result
                return QueryOutcome(
                    header=out.header,
                    rows=out.rows,
                    ms=out.ms,
                    server_ms=out.server_ms,
                    cypher=cypher,
                    params=params,
                )
        return QueryOutcome(header=[], rows=[], ms=0.0, cypher=cypher, params=params)

    def write(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome:
        raise AssertionError("an agent tool tried to write to the graph")

    # ---- helpers for assertions
    def params_for(self, key: str) -> dict[str, Any]:
        """Params of the most recent call whose Cypher contains `key`."""
        for cypher, params in reversed(self.calls):
            if key in cypher:
                return params
        raise AssertionError(f"no query containing {key!r} was run")

    def count(self, key: str) -> int:
        return sum(1 for cypher, _ in self.calls if key in cypher)
