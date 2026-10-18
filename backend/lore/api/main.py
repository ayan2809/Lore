"""FastAPI app factory. Run with:  uv run uvicorn lore.api.main:app --reload"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lore import actions
from lore.api import deps
from lore.api.ratelimit import RateLimiter
from lore.api.routes import router
from lore.config import Settings, get_settings
from lore.db import GraphLike
from lore.observability import log_event


def _count(graph: GraphLike, cypher: str) -> int:
    """Run a count query. FalkorDB refuses to READ a graph that does not exist yet ("Invalid graph
    operation on empty key"), which is exactly the state of a brand-new database: count 0."""
    try:
        rows = graph.ro(cypher).rows
    except Exception as exc:
        if "empty key" in str(exc).lower():
            return 0
        raise
    return int(rows[0][0]) if rows else 0


def graph_needs_loading(graph: GraphLike) -> bool:
    """True when the data has not been loaded (or a load stopped half way).

    The graph counts as loaded when it has Service nodes AND Chunk nodes: the loader writes the
    nodes first and the embedded chunks later, so Services alone mean an interrupted load.
    The loader only uses MERGE, so loading again on top of a partial graph is safe.
    """
    services = _count(graph, "MATCH (s:Service) RETURN count(s)")
    chunks = _count(graph, "MATCH (c:Chunk) RETURN count(c)")
    return not (services > 0 and chunks > 0)


def load_data_if_empty(graph: GraphLike, settings: Settings) -> None:
    """Load backend/data into the graph if it is empty. Runs in a background thread: it never
    raises, and it logs its progress with log_event (watch `/lore/api` in CloudWatch)."""
    started = time.monotonic()
    try:
        if not graph_needs_loading(graph):
            log_event(event="load_on_start_skipped", reason="graph already loaded")
            return
        fake = settings.fake_embeddings
        if not fake and not settings.gemini_api_key:
            log_event(event="load_on_start_skipped", reason="no Gemini key for real embeddings")
            return
        log_event(event="load_on_start_begin", fake_embeddings=fake)
        from lore.loader import load  # imported here: only needed when we really load

        stats = load.load_all(
            graph,
            fake_embeddings=fake,
            embed_dim=settings.embed_dim,
            log=lambda message: log_event(
                event="load_on_start_progress", message=message,
                seconds=round(time.monotonic() - started, 1),
            ),
        )
        log_event(event="load_on_start_done", chunks=stats.get("chunks"),
                  seconds=round(time.monotonic() - started, 1))
    except Exception as exc:  # the API keeps serving (health, replays) even if the load fails
        log_event(event="load_on_start_failed", error=str(exc),
                  seconds=round(time.monotonic() - started, 1))


def start_load_on_start(graph: GraphLike, settings: Settings) -> threading.Thread:
    """Start the load in a daemon thread and return at once, so /api/health answers immediately."""
    thread = threading.Thread(
        target=load_data_if_empty, args=(graph, settings), name="load-on-start", daemon=True
    )
    thread.start()
    return thread


async def startup_checks(settings: Settings) -> None:
    """Log what is available. Never raises: with FalkorDB or Gemini down the API still serves
    replays, personas and health."""
    graph = await asyncio.to_thread(deps.get_graph, settings)
    falkordb_ok = False
    if graph is not None:
        try:
            await asyncio.wait_for(asyncio.to_thread(graph.ro, "RETURN 1"), 3)
            falkordb_ok = True
            actions.configure(graph)  # from now on proposed actions are saved as graph nodes
        except Exception as exc:
            if "empty key" in str(exc).lower():
                # The server answered, there is just no graph yet (a new, empty database).
                falkordb_ok = True
                actions.configure(graph)
            else:
                log_event(event="falkordb_check_failed", error=str(exc))
    if settings.load_on_start == "if_empty" and falkordb_ok:
        start_load_on_start(graph, settings)  # background: never delays startup or /api/health
    log_event(event="startup", falkordb=falkordb_ok, gemini=bool(settings.gemini_api_key),
              replay_mode=settings.force_replay or not settings.gemini_api_key,
              session_secret_is_default=settings.session_secret == "dev-only-change-me")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await startup_checks(settings)
        yield

    app = FastAPI(title="Lore", lifespan=lifespan)
    # Routes read settings through Depends(get_settings); make that the settings given here.
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.limiter = RateLimiter()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # the session cookie must cross from the frontend origin
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
