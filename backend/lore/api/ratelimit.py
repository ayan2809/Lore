"""Tiny in-memory per-IP token bucket (plan section 14, Day 4: protect the Gemini bill).

Applied to POST /investigations and POST /ask. State lives in one process, which is fine for a
single-task demo. Each IP gets `limit` requests per minute, refilled continuously.
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


def _strip_port(address: str) -> str:
    """'203.0.113.7:4821' -> '203.0.113.7'. CloudFront sends IPv6 without brackets, as
    '2001:db8::1:443', so the port is whatever follows the LAST colon. '[2001:db8::1]:443' (the
    bracketed form) is handled too."""
    address = address.strip()
    if address.startswith("["):
        return address[1:].split("]", 1)[0]
    head, sep, _port = address.rpartition(":")
    return head if sep else address


def client_ip(request: Request) -> str:
    """The caller's IP address, used as the rate-limit key.

    On AWS the request reaches us through CloudFront and an ALB, so `request.client.host` is the
    load balancer. CloudFront adds `CloudFront-Viewer-Address` ("ip:port") with the real viewer.
    These headers are only trustworthy because the ALB rejects every request that lacks the secret
    `X-Origin-Verify` header (which only our CloudFront distribution sends); otherwise anyone could
    send a fake header and dodge the limit. Fallbacks: the first `X-Forwarded-For` entry (the
    original client when the ALB is the only proxy), then the direct peer (local runs).
    """
    viewer = request.headers.get("cloudfront-viewer-address")
    if viewer:
        return _strip_port(viewer)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Dependency: raises 429 when this IP is over its per-minute budget."""
    wait = request.app.state.limiter.allow(client_ip(request), settings.rate_limit_per_minute)
    if wait:
        raise HTTPException(
            429, "Too many requests, slow down.", headers={"Retry-After": str(int(wait) + 1)}
        )
