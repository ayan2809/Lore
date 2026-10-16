"""FastAPI app factory. Run with:  uv run uvicorn lore.api.main:app --reload"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lore import actions
from lore.api import deps
from lore.api.ratelimit import RateLimiter
from lore.api.routes import router
from lore.config import Settings, get_settings
from lore.observability import log_event


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
            log_event(event="falkordb_check_failed", error=str(exc))
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
