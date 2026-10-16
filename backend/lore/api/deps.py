"""FastAPI dependencies. Tests replace these with fakes via `app.dependency_overrides`."""

# ruff: noqa: B008  (FastAPI's `Depends(...)` as a default value is the standard pattern)

from __future__ import annotations

from fastapi import Depends, HTTPException

from lore.config import Settings, get_settings
from lore.db import GraphLike
from lore.observability import log_event


def get_graph(settings: Settings = Depends(get_settings)) -> GraphLike | None:
    """The FalkorDB client, or None if it cannot be reached (the API must still start)."""
    from lore import db

    try:
        return db.get_graph(settings)
    except Exception as exc:
        log_event(event="falkordb_unavailable", error=str(exc))
        return None


def require_graph(graph: GraphLike | None) -> GraphLike:
    """Use inside a route that cannot work without the graph."""
    if graph is None:
        raise HTTPException(503, "FalkorDB is not reachable")
    return graph


def get_llm(settings: Settings = Depends(get_settings)):
    """The Gemini wrapper, or None if there is no API key (then investigations use replay)."""
    if not settings.gemini_api_key:
        return None
    from lore import llm

    try:
        return llm.get_llm(settings)
    except Exception as exc:
        log_event(event="gemini_unavailable", error=str(exc))
        return None
