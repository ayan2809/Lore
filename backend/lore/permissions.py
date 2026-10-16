"""Who is looking (plan section 6).

The permission CHECK itself lives inside every content-returning Cypher query:

    WHERE src.access_level IN $open_levels
       OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)

This module only decides who the viewer is and which levels are open to them.
`viewer` and `open_levels` are added to query params by the server (tools.py), never by the model.
"""

from __future__ import annotations

from lore.models import Persona, Viewer

PERSONAS: dict[str, Persona] = {
    p.id: p
    for p in [
        Persona(
            id="arjun",
            person_id="person:arjun",
            name="Arjun Mehta",
            role="On-call engineer, Checkout (joined 3 weeks ago)",
            can_see="public + internal + Checkout and on-call channels",
        ),
        Persona(
            id="dana",
            person_id="person:dana",
            name="Dana Okafor",
            role="Incident commander + security role",
            can_see="everything except HR",
        ),
        Persona(
            id="sam",
            person_id="person:sam",
            name="Sam Rivera",
            role="Contractor",
            can_see="public only",
            employment="contractor",
        ),
        Persona(
            id="marco",
            person_id="person:marco",
            name="Marco Bianchi",
            role="Moved from Pricing to Data in August",
            can_see="lost #pricing-private when he moved",
        ),
    ]
}

DEFAULT_PERSONA = "arjun"


def viewer_for(persona_id: str | None) -> Viewer:
    """Map a session's persona id to a Viewer. Unknown ids fall back to the least-privileged one."""
    persona = PERSONAS.get(persona_id or DEFAULT_PERSONA) or PERSONAS["sam"]
    return persona.viewer()


def permission_params(viewer: Viewer) -> dict[str, object]:
    """Params every content-returning query receives. Merged in by tools.run_query()."""
    return {"viewer": viewer.id, "open_levels": viewer.open_levels}
