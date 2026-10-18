"""API tests: no FalkorDB, no Gemini. A fake supervisor and fake graph replace both."""

import shutil
import sys
import tempfile
import types
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import lore
from lore import actions
from lore.api import deps, runs
from lore.api.main import create_app
from lore.api.ratelimit import client_ip
from lore.api.runs import RunRegistry
from lore.config import Settings, get_settings
from lore.db import QueryOutcome
from lore.models import Report, RunSummary, StepEvent


class FakeGraph:
    def ro(self, cypher, params=None):
        return QueryOutcome(header=[], rows=[], ms=0.0)

    write = ro


def make_fake_supervisor(seen: list):
    """Emits 3 events then `done`, using its own investigation id (like the real supervisor)."""

    async def fake_supervisor(alert_id, viewer, *, mode, llm, graph, emit, settings=None):
        seen.append((alert_id, viewer.id, mode))
        inner = "inv:inner"
        for seq, (type_, payload) in enumerate([
            ("investigation_started", {"alert_id": alert_id, "viewer_id": viewer.id,
                                        "mode": mode, "replay": False}),
            ("agent_started", {"agent": "triage", "goal": "g"}),
            ("tool_call", {"tool": "find_entity", "reason": "r", "args": {}}),
        ]):
            await emit(StepEvent(type=type_, investigation_id=inner, seq=seq, ts=0.0,
                                 payload=payload))
        summary = RunSummary(investigation_id=inner, steps=1)
        await emit(StepEvent(type="done", investigation_id=inner, seq=3, ts=0.0,
                             payload=summary.model_dump()))
        return Report(summary="s"), summary

    return fake_supervisor


SAMPLE_REPLAY = Path(__file__).resolve().parents[1] / "replays" / "sample_story_a.replay.json"


def build_client(limit: int = 100, **settings_extra):
    # Tests see only the hand-written sample, not the real recordings in backend/replays.
    if "replay_dir" not in settings_extra:
        tmp = Path(tempfile.mkdtemp())
        shutil.copy(SAMPLE_REPLAY, tmp / SAMPLE_REPLAY.name)
        settings_extra["replay_dir"] = str(tmp)
    settings = Settings(session_secret="test-secret", rate_limit_per_minute=limit, _env_file=None,
                        **settings_extra)
    app = create_app(settings)
    seen: list = []
    registry = RunRegistry(supervisor=make_fake_supervisor(seen), replay_speed=10_000)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_graph] = lambda: FakeGraph()
    app.dependency_overrides[deps.get_llm] = lambda: object()  # "Gemini is available"
    app.dependency_overrides[runs.get_registry] = lambda: registry
    return TestClient(app), seen, registry


@pytest.fixture
def api():
    client, seen, _ = build_client()
    with client:  # `with` keeps the event loop alive so background runs can finish
        yield client, seen


def event_names(response_text: str) -> list[str]:
    return [line.removeprefix("event:").strip() for line in response_text.splitlines()
            if line.startswith("event:")]


def login(client, persona):
    assert client.post("/api/session", json={"persona": persona}).status_code == 200


# ------------------------------------------------------------------ session and personas


def test_session_cookie_sets_and_reads_persona(api):
    client, _ = api
    login(client, "dana")
    assert "lore_session" in client.cookies
    assert client.get("/api/session").json()["persona"]["id"] == "dana"


def session_cookie_header(client) -> str:
    return client.post("/api/session", json={"persona": "dana"}).headers["set-cookie"].lower()


def test_session_cookie_is_httponly_lax_and_not_secure_by_default(api):
    client, _ = api
    header = session_cookie_header(client)
    assert "httponly" in header and "samesite=lax" in header
    assert "secure" not in header


def test_session_cookie_is_secure_when_configured():
    client, _, _ = build_client(cookie_secure=True)
    with client:
        header = session_cookie_header(client)
    assert "httponly" in header and "samesite=lax" in header and "secure" in header


def test_cors_origins_no_longer_change_the_cookie_flags():
    client, _, _ = build_client(cors_origins=["https://example.vercel.app"])
    with client:
        header = session_cookie_header(client)
    assert "samesite=lax" in header and "secure" not in header


def test_default_and_tampered_cookie_fall_back_to_default_persona(api):
    client, _ = api
    assert client.get("/api/session").json()["persona"]["id"] == "arjun"
    client.cookies.set("lore_session", "not-a-signed-value")
    assert client.get("/api/session").json()["persona"]["id"] == "arjun"


def test_unknown_persona_rejected(api):
    client, _ = api
    assert client.post("/api/session", json={"persona": "mallory"}).status_code == 404


def test_personas_endpoint(api):
    client, _ = api
    ids = {p["id"] for p in client.get("/api/personas").json()}
    assert ids == {"arjun", "dana", "sam", "marco"}


def test_health_reports_flags(api):
    client, _ = api
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["falkordb"] is True


# ------------------------------------------------------------------ investigations and SSE


def test_investigation_streams_events_then_done(api):
    client, seen = api
    login(client, "arjun")
    iid = client.post("/api/investigations", json={"alert_id": "A-3001", "mode": "graph"}).json()[
        "investigation_id"
    ]
    with client.stream("GET", f"/api/investigations/{iid}/events") as resp:
        text = "".join(resp.iter_text())
    assert event_names(text) == [
        "investigation_started", "agent_started", "tool_call", "done"
    ]
    assert "inv:inner" not in text  # the client only sees the API's investigation id
    assert seen == [("A-3001", "person:arjun", "graph")]
    # a late subscriber gets the whole history again
    with client.stream("GET", f"/api/investigations/{iid}/events") as resp:
        assert len(event_names("".join(resp.iter_text()))) == 4
    detail = client.get(f"/api/investigations/{iid}").json()
    assert detail["summary"]["steps"] == 1 and detail["actions"] == []


def test_viewer_cannot_be_injected_by_body_or_query(api):
    client, seen = api
    login(client, "arjun")
    client.post(
        "/api/investigations?viewer=person:dana&persona=dana",
        json={"alert_id": "A-3001", "mode": "graph", "viewer": "person:dana", "persona": "dana"},
    )
    assert client.get("/api/session?persona=dana").json()["persona"]["id"] == "arjun"
    client.get("/api/investigations/none")
    assert seen[-1][1] == "person:arjun"


def test_other_personas_cannot_read_a_run(api):
    client, _ = api
    login(client, "arjun")
    iid = client.post("/api/investigations", json={"alert_id": "A-3001"}).json()["investigation_id"]
    login(client, "sam")
    assert client.get(f"/api/investigations/{iid}").status_code == 404
    assert client.get(f"/api/investigations/{iid}/events").status_code == 404


def test_replay_flag_plays_sample_recording(api):
    client, seen = api
    login(client, "arjun")
    iid = client.post(
        "/api/investigations", json={"alert_id": "A-3001", "replay": True}
    ).json()["investigation_id"]
    with client.stream("GET", f"/api/investigations/{iid}/events") as resp:
        text = "".join(resp.iter_text())
    names = event_names(text)
    assert names[0] == "investigation_started" and names[-1] == "done"
    assert '"replay": true' in text and "report" in names and "action_proposed" in names
    assert seen == []  # the supervisor was never called
    detail = client.get(f"/api/investigations/{iid}").json()
    assert detail["report"]["root_cause"] == "pr:482" and detail["summary"]["replay"] is True
    assert len(detail["actions"]) == 1


def test_replay_without_recording_sends_error_then_done(api):
    client, _ = api
    login(client, "sam")
    iid = client.post("/api/investigations", json={"alert_id": "A-3001", "replay": True}).json()[
        "investigation_id"
    ]
    with client.stream("GET", f"/api/investigations/{iid}/events") as resp:
        assert event_names("".join(resp.iter_text())) == ["error", "done"]


# ------------------------------------------------------------------ actions


def fake_policy(monkeypatch, allowed: bool, reason: str = ""):
    decision = types.SimpleNamespace(allowed=allowed, reason=reason)
    fake = types.SimpleNamespace(
        check_post_audience=lambda graph, channel_id, cited_ids: decision,
        check_request=lambda text: decision,
    )
    monkeypatch.setitem(sys.modules, "lore.policy", fake)
    monkeypatch.setattr(lore, "policy", fake, raising=False)


def test_approve_is_blocked_by_policy(api, monkeypatch):
    client, _ = api
    login(client, "arjun")
    iid = client.post("/api/investigations", json={"alert_id": "A-3001"}).json()["investigation_id"]
    cited = ["thread:pricing-private-0142"]
    action = actions.propose(iid, "slack_post", "#general", "details", cited)
    fake_policy(monkeypatch, False, "#general members cannot see thread:pricing-private-0142")
    body = client.post(f"/api/actions/{action.id}/approve").json()
    assert body["status"] == "blocked"
    assert "cannot see" in body["blocked_reason"]
    # a blocked action can be edited and is proposed again
    edited = client.patch(f"/api/actions/{action.id}", json={"text": "safe text"}).json()
    assert edited["status"] == "proposed"


def test_edit_then_reject(api):
    client, _ = api
    login(client, "arjun")
    iid = client.post("/api/investigations", json={"alert_id": "A-3001"}).json()["investigation_id"]
    action = actions.propose(iid, "github_issue", "owner/repo", "old", ["pr:482"])
    assert client.patch(f"/api/actions/{action.id}", json={"text": "new"}).json()["text"] == "new"
    assert client.post(f"/api/actions/{action.id}/reject").json()["status"] == "rejected"
    assert client.post(f"/api/actions/{action.id}/approve").status_code == 409


def test_actions_of_other_viewers_are_hidden(api):
    client, _ = api
    login(client, "arjun")
    iid = client.post("/api/investigations", json={"alert_id": "A-3001"}).json()["investigation_id"]
    action = actions.propose(iid, "rollback", "deploy:991", "roll back", ["deploy:991"])
    login(client, "sam")
    assert client.post(f"/api/actions/{action.id}/approve").status_code == 404
    assert client.post("/api/actions/action:missing/approve").status_code == 404


# ------------------------------------------------------------------ rate limit


def test_rate_limit_returns_429():
    client, _, _ = build_client(limit=2)
    with client:
        statuses = [
            client.post("/api/investigations", json={"alert_id": "A-3001"}).status_code
            for _ in range(3)
        ]
        assert statuses == [200, 200, 429]
        assert client.get("/api/health").status_code == 200  # other routes are not limited


def make_request(headers: dict[str, str], peer: str | None = "10.20.1.5") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234) if peer else None})


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"CloudFront-Viewer-Address": "203.0.113.7:51234"}, "203.0.113.7"),
        ({"CloudFront-Viewer-Address": "2001:db8::1:443"}, "2001:db8::1"),  # IPv6, no brackets
        ({"CloudFront-Viewer-Address": "[2001:db8::1]:443"}, "2001:db8::1"),
        # CloudFront wins over X-Forwarded-For, which is only a fallback
        ({"CloudFront-Viewer-Address": "203.0.113.7:1", "X-Forwarded-For": "198.51.100.9"},
         "203.0.113.7"),
        ({"X-Forwarded-For": "198.51.100.9, 10.20.1.5"}, "198.51.100.9"),  # first entry
        ({}, "10.20.1.5"),  # no proxy headers: the direct peer
    ],
)
def test_client_ip(headers, expected):
    assert client_ip(make_request(headers)) == expected


def test_client_ip_without_any_information():
    assert client_ip(make_request({}, peer=None)) == "unknown"


def test_rate_limit_is_per_cloudfront_viewer_address():
    client, _, _ = build_client(limit=1)
    with client:
        def post(viewer: str) -> int:
            return client.post("/api/investigations", json={"alert_id": "A-3001"},
                               headers={"CloudFront-Viewer-Address": viewer}).status_code

        assert [post("203.0.113.7:1000"), post("203.0.113.7:2000")] == [200, 429]  # same IP
        assert post("203.0.113.8:1000") == 200  # another visitor has their own budget


def test_supervisor_crash_ends_stream_with_error_then_done():
    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    client, _, registry = build_client()
    registry.supervisor = broken
    with client:
        login(client, "arjun")
        iid = client.post("/api/investigations", json={"alert_id": "A-3001"}).json()[
            "investigation_id"
        ]
        with client.stream("GET", f"/api/investigations/{iid}/events") as resp:
            text = "".join(resp.iter_text())
        assert event_names(text) == ["error", "done"]
        assert "boom" not in text  # internal error text stays in the server log


def test_api_starts_and_serves_when_falkordb_and_gemini_are_missing():
    # Point at a port nothing listens on, so a developer's running FalkorDB (or .env) is ignored.
    settings = Settings(_env_file=None, falkordb_port=1, gemini_api_key=None)
    app = create_app(settings)  # no dependency overrides: the real wiring
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["falkordb"] is False and health["gemini"] is False
        assert health["replay"] is True
        assert len(client.get("/api/alerts").json()) == 2  # static fallback alerts
        assert client.get("/api/graph").status_code == 503
