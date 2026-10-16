"""FalkorDB access.

- `ro()` is the only way agent tools touch the graph: GRAPH.RO_QUERY refuses writes (plan L.8 #8).
- `write()` is for the loader and the memory module only.
- Cypher lives in lore/queries/*.cypher and is loaded by name with `load_query()`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from lore.config import Settings, get_settings

QUERIES_DIR = Path(__file__).parent / "queries"


@cache
def load_query(name: str) -> str:
    """Return the text of lore/queries/<name>.cypher (comments kept: they are documentation)."""
    return (QUERIES_DIR / f"{name}.cypher").read_text()


@dataclass
class QueryOutcome:
    header: list[str]
    rows: list[list[Any]]
    ms: float  # wall-clock time measured around the call
    server_ms: float | None = None  # FalkorDB's own reported time, if available
    cypher: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def dicts(self) -> list[dict[str, Any]]:
        return [dict(zip(self.header, row, strict=False)) for row in self.rows]


class GraphLike(Protocol):
    """What tools need. The real implementation is `GraphClient`; tests use a fake."""

    def ro(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome: ...

    def write(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome: ...


class GraphClient:
    def __init__(self, settings: Settings | None = None, graph_name: str | None = None):
        from falkordb import FalkorDB  # imported lazily so unit tests run without the package

        self.settings = settings or get_settings()
        self._db = FalkorDB(
            host=self.settings.falkordb_host,
            port=self.settings.falkordb_port,
            password=self.settings.falkordb_password,
        )
        self.graph_name = graph_name or self.settings.graph_name
        self._graph = self._db.select_graph(self.graph_name)

    def ro(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome:
        start = time.perf_counter()
        res = self._graph.ro_query(cypher, params or {}, timeout=self.settings.query_timeout_ms)
        return self._outcome(res, start, cypher, params)

    def write(self, cypher: str, params: dict[str, Any] | None = None) -> QueryOutcome:
        start = time.perf_counter()
        res = self._graph.query(cypher, params or {})
        return self._outcome(res, start, cypher, params)

    def delete_graph(self) -> None:
        """Drop the whole tenant graph. Used by `make reset` only."""
        try:
            self._graph.delete()
        except Exception:  # graph may not exist yet
            pass

    @staticmethod
    def _outcome(res: Any, start: float, cypher: str, params: dict | None) -> QueryOutcome:
        ms = (time.perf_counter() - start) * 1000
        header = [h[1] if isinstance(h, list | tuple) else str(h) for h in (res.header or [])]
        server_ms = getattr(res, "run_time_ms", None)  # FalkorDB's internal execution time
        return QueryOutcome(
            header=header,
            rows=list(res.result_set or []),
            ms=ms,
            server_ms=server_ms,
            cypher=cypher,
            params=params or {},
        )


_clients: dict[tuple, GraphClient] = {}


def get_graph(settings: Settings | None = None) -> GraphClient:
    """One shared client per (host, port, graph), created on first use."""
    settings = settings or get_settings()
    key = (settings.falkordb_host, settings.falkordb_port, settings.graph_name)
    if key not in _clients:
        _clients[key] = GraphClient(settings)
    return _clients[key]
