"""Action lifecycle: propose -> edit -> approve/reject, with httpx mocked."""

import json
import sys
import types

import httpx
import pytest

import lore
from lore import actions
from lore.config import Settings
from lore.db import QueryOutcome


def fake_policy(monkeypatch, allowed=True, reason=""):
    decision = types.SimpleNamespace(allowed=allowed, reason=reason)
    fake = types.SimpleNamespace(
        check_post_audience=lambda graph, channel_id, cited: decision,
        check_issue_citations=lambda graph, cited: decision,
    )
    monkeypatch.setitem(sys.modules, "lore.policy", fake)
    monkeypatch.setattr(lore, "policy", fake, raising=False)


@pytest.fixture
def http(monkeypatch):
    """Replace the network with a MockTransport that records requests."""
    calls: list[httpx.Request] = []
    state = {"status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(state["status"], json={"html_url": "https://github.com/o/r/issues/1"})

    monkeypatch.setattr(actions, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(actions, "BACKOFF_S", 0)
    return calls, state


def settings(**kw):
    return Settings(_env_file=None, **kw)


async def test_no_webhook_means_simulated(monkeypatch, http):
    fake_policy(monkeypatch)
    a = actions.propose("inv:t1", "slack_post", "#incidents", "hello", ["pr:482"])
    assert a.status == "proposed"
    done = await actions.approve(a.id, None, settings())
    assert done.status == "sent" and done.simulated is True
    assert "Simulated" in done.blocked_reason
    assert http[0] == []  # nothing left the machine


async def test_rollback_is_always_simulated(monkeypatch, http):
    s = settings(slack_webhook_url="https://hooks.example/x", github_token="t", github_repo="o/r")
    a = actions.propose("inv:t2", "rollback", "deploy:991", "roll back", ["deploy:991"])
    assert a.simulated is True
    done = await actions.approve(a.id, None, s)
    assert done.status == "sent" and done.simulated is True
    assert http[0] == []


async def test_edit_then_approve_sends_edited_text(monkeypatch, http):
    fake_policy(monkeypatch)
    calls, _ = http
    s = settings(slack_webhook_url="https://hooks.example/x")
    a = actions.propose("inv:t3", "slack_post", "#incidents", "draft", ["pr:482"])
    actions.edit(a.id, "final text")
    done = await actions.approve(a.id, None, s)
    assert done.status == "sent" and done.simulated is False
    assert json.loads(calls[0].content) == {"text": "final text"}
    assert str(calls[0].url) == "https://hooks.example/x"


async def test_policy_block_sends_nothing(monkeypatch, http):
    fake_policy(monkeypatch, allowed=False, reason="channel includes people who cannot see it")
    s = settings(slack_webhook_url="https://hooks.example/x")
    a = actions.propose("inv:t4", "slack_post", "#general", "secret", ["thread:sec-incidents-0007"])
    done = await actions.approve(a.id, None, s)
    assert done.status == "blocked" and "cannot see" in done.blocked_reason
    assert http[0] == []


async def test_policy_error_fails_closed(monkeypatch, http):
    def boom(graph, channel_id, cited):
        raise RuntimeError("graph down")

    fake = types.SimpleNamespace(check_post_audience=boom)
    monkeypatch.setitem(sys.modules, "lore.policy", fake)
    monkeypatch.setattr(lore, "policy", fake, raising=False)
    a = actions.propose("inv:t5", "slack_post", "#incidents", "x", ["pr:482"])
    done = await actions.approve(a.id, None, settings(slack_webhook_url="https://hooks.example/x"))
    assert done.status == "blocked" and http[0] == []


async def test_github_issue_returns_url_and_uses_configured_repo(monkeypatch, http):
    fake_policy(monkeypatch)
    calls, _ = http
    s = settings(github_token="tok", github_repo="kettle/ops")
    a = actions.propose("inv:t6", "github_issue", "attacker/repo", "body", ["pr:482"], title="T")
    done = await actions.approve(a.id, None, s)
    assert done.status == "sent" and done.result_url.endswith("/issues/1")
    assert str(calls[0].url) == "https://api.github.com/repos/kettle/ops/issues"
    assert calls[0].headers["authorization"] == "Bearer tok"
    assert json.loads(calls[0].content) == {"title": "T", "body": "body"}


async def test_server_errors_are_retried_then_marked_failed(http):
    calls, state = http
    state["status"] = 503
    s = settings(github_token="tok", github_repo="kettle/ops")
    a = actions.propose("inv:t7", "github_issue", "kettle/ops", "body", [])
    done = await actions.approve(a.id, None, s)
    assert done.status == "failed" and "503" in done.blocked_reason
    assert len(calls) == actions.MAX_ATTEMPTS
    state["status"] = 200  # a failed action can be approved again
    assert (await actions.approve(a.id, None, s)).status == "sent"


async def test_client_errors_are_not_retried(http):
    calls, state = http
    state["status"] = 401
    a = actions.propose("inv:t8", "github_issue", "x", "b", [])
    done = await actions.approve(a.id, None, settings(github_token="bad", github_repo="o/r"))
    assert done.status == "failed" and len(calls) == 1


async def test_cannot_approve_twice_or_after_reject(http):
    a = actions.propose("inv:t9", "rollback", "deploy:1", "x", [])
    await actions.approve(a.id, None, settings())
    with pytest.raises(actions.ActionStateError):
        await actions.approve(a.id, None, settings())
    b = actions.propose("inv:t9", "rollback", "deploy:2", "x", [])
    assert actions.reject(b.id).status == "rejected"
    with pytest.raises(actions.ActionStateError):
        await actions.approve(b.id, None, settings())


def test_propose_saves_action_node_when_graph_configured():
    class RecordingGraph:
        def __init__(self):
            self.writes = []

        def write(self, cypher, params=None):
            self.writes.append((cypher, params))
            return QueryOutcome(header=[], rows=[], ms=0)

    graph = RecordingGraph()
    actions.configure(graph)
    try:
        a = actions.propose("inv:t10", "slack_post", "#incidents", "hi", ["pr:482"])
        actions.edit(a.id, "hi again")
    finally:
        actions.configure(None)
    assert len(graph.writes) == 2
    cypher, params = graph.writes[-1]
    assert "MERGE (a:Action" in cypher
    assert params["id"] == a.id and params["text"] == "hi again" and params["status"] == "proposed"


async def test_github_issue_citing_a_restricted_source_is_blocked_until_the_citation_is_dropped(
    http,
):
    """FIX_LOG F-09: the demo repo is public, so restricted sources may not be cited there."""

    class Graph:
        def ro(self, cypher, params):
            bad = [i for i in params["cited_ids"] if i.startswith("thread:pricing-private")]
            return QueryOutcome(["source_id", "access_level"], [[i, "restricted"] for i in bad], 1)

    s = settings(github_token="t", github_repo="o/r")
    cited = ["pr:482", "thread:pricing-private-0142"]
    a = actions.propose("inv:t9", "github_issue", "o/r", "body", cited, title="T")
    blocked = await actions.approve(a.id, Graph(), s)
    assert blocked.status == "blocked" and "thread:pricing-private-0142" in blocked.blocked_reason
    assert http[0] == []  # nothing was sent

    actions.edit(a.id, "body without the private part", cited_ids=["pr:482", "pr:999"])
    assert actions.get(a.id).cited_ids == ["pr:482"]  # can drop citations, never add new ones
    assert (await actions.approve(a.id, Graph(), s)).status == "sent"
