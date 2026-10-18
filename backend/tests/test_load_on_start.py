"""LORE_LOAD_ON_START=if_empty: load the data in a background thread when the graph is empty.

No FalkorDB and no Gemini: a fake graph answers the count queries and the loader is monkeypatched.
"""

import threading

import pytest
from fastapi.testclient import TestClient

from lore.api import deps
from lore.api import main as api_main
from lore.api.main import create_app, graph_needs_loading, load_data_if_empty
from lore.config import Settings
from lore.db import QueryOutcome
from lore.loader import load


class CountingGraph:
    """Answers the two count queries. `services` / `chunks` are what the 'database' holds.
    `no_graph_yet=True` behaves like a brand-new FalkorDB: reading a graph that does not exist
    raises "Invalid graph operation on empty key" (seen on the real server)."""

    def __init__(self, services: int = 0, chunks: int = 0, no_graph_yet: bool = False):
        self.counts = {"Service": services, "Chunk": chunks}
        self.no_graph_yet = no_graph_yet
        self.queries: list[str] = []

    def ro(self, cypher, params=None):
        self.queries.append(cypher)
        if self.no_graph_yet:
            raise RuntimeError("Invalid graph operation on empty key")
        for label, n in self.counts.items():
            if f":{label})" in cypher:
                return QueryOutcome(header=["n"], rows=[[n]], ms=0.0)
        return QueryOutcome(header=[], rows=[], ms=0.0)

    def write(self, cypher, params=None, timeout_ms=None):
        raise AssertionError("the loader is faked in these tests")


def settings_for(**extra) -> Settings:
    return Settings(_env_file=None, falkordb_port=1, **extra)


def fake_loader(monkeypatch, calls: list, gate: threading.Event | None = None):
    def load_all(graph, data_dir=None, *, fake_embeddings, embed_dim=None, log=print, **_):
        calls.append((fake_embeddings, embed_dim))
        log("nodes: 943")
        if gate is not None:
            gate.wait(timeout=5)
        log("chunks: 579")
        return {"chunks": 579}

    monkeypatch.setattr(load, "load_all", load_all)


def logged_events(monkeypatch) -> list[dict]:
    events: list[dict] = []
    monkeypatch.setattr(api_main, "log_event", lambda **fields: events.append(fields))
    return events


# ---------------------------------------------------------------- is the graph empty?


def test_empty_graph_needs_loading():
    assert graph_needs_loading(CountingGraph(0, 0)) is True


def test_a_brand_new_database_with_no_graph_yet_needs_loading():
    assert graph_needs_loading(CountingGraph(no_graph_yet=True)) is True


def test_other_database_errors_are_not_mistaken_for_an_empty_graph():
    class Down(CountingGraph):
        def ro(self, cypher, params=None):
            raise ConnectionError("connection refused")

    with pytest.raises(ConnectionError):
        graph_needs_loading(Down())


def test_loaded_graph_does_not_need_loading():
    assert graph_needs_loading(CountingGraph(65, 579)) is False


def test_services_without_chunks_is_a_half_finished_load():
    assert graph_needs_loading(CountingGraph(65, 0)) is True


# ---------------------------------------------------------------- the loading itself


def test_empty_graph_is_loaded_with_real_embeddings(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    events = logged_events(monkeypatch)
    load_data_if_empty(CountingGraph(), settings_for(gemini_api_key="k", embed_dim=768))
    assert calls == [(False, 768)]
    names = [e["event"] for e in events]
    assert names == [
        "load_on_start_begin",
        "load_on_start_progress",
        "load_on_start_progress",
        "load_on_start_done",
    ]
    assert events[1]["message"] == "nodes: 943"
    assert "api_key" not in str(events)  # the key is never logged


def test_fake_embeddings_setting_is_respected_and_needs_no_key(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    logged_events(monkeypatch)
    load_data_if_empty(CountingGraph(), settings_for(fake_embeddings=True))
    assert calls == [(True, 768)]


def test_loaded_graph_is_left_alone(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    events = logged_events(monkeypatch)
    load_data_if_empty(CountingGraph(65, 579), settings_for(gemini_api_key="k"))
    assert calls == []
    assert events[-1]["event"] == "load_on_start_skipped"


def test_no_key_and_no_fake_embeddings_skips_instead_of_crashing(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    events = logged_events(monkeypatch)
    load_data_if_empty(CountingGraph(), settings_for(gemini_api_key=None))
    assert calls == [] and events[-1]["event"] == "load_on_start_skipped"


def test_a_failing_load_is_logged_not_raised(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(load, "load_all", broken)
    events = logged_events(monkeypatch)
    load_data_if_empty(CountingGraph(), settings_for(gemini_api_key="k"))
    assert events[-1]["event"] == "load_on_start_failed"
    assert "embedding service down" in events[-1]["error"]


# ---------------------------------------------------------------- startup wiring


def test_startup_does_not_wait_for_the_load_and_health_answers_meanwhile(monkeypatch):
    gate = threading.Event()
    calls: list = []
    fake_loader(monkeypatch, calls, gate)
    logged_events(monkeypatch)
    graph = CountingGraph()
    monkeypatch.setattr(deps, "get_graph", lambda settings: graph)
    settings = settings_for(gemini_api_key="k", load_on_start="if_empty")
    try:
        with TestClient(create_app(settings)) as client:  # startup returned while load is blocked
            assert not gate.is_set()
            assert client.get("/api/health").status_code == 200
            threads = [t for t in threading.enumerate() if t.name == "load-on-start"]
            assert len(threads) == 1 and threads[0].daemon
    finally:
        gate.set()
    for t in threading.enumerate():
        if t.name == "load-on-start":
            t.join(timeout=5)
    assert calls == [(False, 768)]


def test_startup_loads_a_brand_new_database_that_has_no_graph_yet(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    logged_events(monkeypatch)
    graph = CountingGraph(no_graph_yet=True)
    monkeypatch.setattr(deps, "get_graph", lambda settings: graph)
    with TestClient(create_app(settings_for(gemini_api_key="k", load_on_start="if_empty"))):
        pass
    for t in threading.enumerate():
        if t.name == "load-on-start":
            t.join(timeout=5)
    assert calls == [(False, 768)]


def test_default_setting_never_loads(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    logged_events(monkeypatch)
    monkeypatch.setattr(deps, "get_graph", lambda settings: CountingGraph())
    with TestClient(create_app(settings_for(gemini_api_key="k"))):
        pass
    assert calls == [] and not [t for t in threading.enumerate() if t.name == "load-on-start"]


def test_no_load_when_falkordb_is_unreachable(monkeypatch):
    calls: list = []
    fake_loader(monkeypatch, calls)
    logged_events(monkeypatch)
    monkeypatch.setattr(deps, "get_graph", lambda settings: None)
    with TestClient(create_app(settings_for(gemini_api_key="k", load_on_start="if_empty"))):
        pass
    assert calls == []
