"""The login session: a signed cookie `lore_session` holding {"persona": "arjun"}.

The viewer is ALWAYS derived from this cookie. No route reads a viewer from a request body or
query string, and nothing the model produces can change it (plan section 6).
"""

# ruff: noqa: B008  (FastAPI's `Depends(...)` as a default value is the standard pattern)

from __future__ import annotations

from fastapi import Depends, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer

from lore.config import Settings, get_settings
from lore.models import Viewer
from lore.permissions import DEFAULT_PERSONA, PERSONAS, viewer_for

COOKIE_NAME = "lore_session"
MAX_AGE_S = 7 * 24 * 3600


def _serializer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret, salt="lore-session")


def set_persona(response: Response, persona_id: str, settings: Settings) -> None:
    """Write the signed cookie.

    The page and the API share one origin (CloudFront serves both), so SameSite=Lax is enough.
    `Secure` follows LORE_COOKIE_SECURE: true behind HTTPS, false for http://localhost.
    """
    response.set_cookie(
        COOKIE_NAME,
        _serializer(settings).dumps({"persona": persona_id}),
        max_age=MAX_AGE_S,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def current_persona(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Persona id from the cookie. Missing, tampered or unknown values fall back to the default."""
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        try:
            persona = _serializer(settings).loads(raw).get("persona")
        except (BadSignature, AttributeError):
            persona = None
        if persona in PERSONAS:
            return persona
    return DEFAULT_PERSONA


def current_viewer(persona: str = Depends(current_persona)) -> Viewer:
    return viewer_for(persona)
