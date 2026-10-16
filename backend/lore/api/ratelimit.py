"""Tiny in-memory per-IP token bucket (plan section 14, Day 4: protect the Gemini bill).

Applied to POST /investigations and POST /ask. State lives in one process, which is fine for a
single-VM demo. Each IP gets `limit` requests per minute, refilled continuously.
"""

# ruff: noqa: B008  (FastAPI's `Depends(...)` as a default value is the standard pattern)

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request

from lore.config import Settings, get_settings


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, last_seen)

    def allow(self, key: str, per_minute: int, now: float | None = None) -> float:
        """Return 0.0 if allowed, else the seconds to wait before the next request is allowed."""
        now = time.monotonic() if now is None else now
        tokens, last = self._buckets.get(key, (float(per_minute), now))
        tokens = min(float(per_minute), tokens + (now - last) * per_minute / 60)
        if tokens >= 1:
            self._buckets[key] = (tokens - 1, now)
            return 0.0
        self._buckets[key] = (tokens, now)
        return (1 - tokens) * 60 / per_minute


def client_ip(request: Request) -> str:
    """Behind Caddy the real client is the LAST X-Forwarded-For entry (the one Caddy appended)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Dependency: raises 429 when this IP is over its per-minute budget."""
    wait = request.app.state.limiter.allow(client_ip(request), settings.rate_limit_per_minute)
    if wait:
        raise HTTPException(
            429, "Too many requests, slow down.", headers={"Retry-After": str(int(wait) + 1)}
        )
