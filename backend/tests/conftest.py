"""Shared fixtures.

- `fake_graph` / `make_ctx`: a ToolContext over a FakeGraph, for unit tests.
- `viewers`: the four demo personas as Viewer objects.
- Tests marked `integration` are skipped automatically when FalkorDB is not reachable at
  LORE_FALKORDB_HOST:PORT (so `pytest` works on a laptop without Docker).
"""

from __future__ import annotations

import socket

import pytest

from lore.config import get_settings
from lore.models import Viewer
from lore.permissions import PERSONAS, viewer_for
from lore.tools import ToolContext
from tests.fakes import FakeGraph


def _falkordb_reachable() -> bool:
    settings = get_settings()
    try:
        with socket.create_connection((settings.falkordb_host, settings.falkordb_port), 0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def falkordb_available() -> bool:
    return _falkordb_reachable()


def pytest_collection_modifyitems(config, items):
    """Skip `integration` tests when there is no FalkorDB to talk to."""
    if _falkordb_reachable():
        return
    skip = pytest.mark.skip(reason="FalkorDB is not reachable (set LORE_FALKORDB_HOST/PORT)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def _integration_graph_copy(request):
    """Run integration tests on a throwaway copy of the loaded graph, never on the graph itself.

    Some integration tests write agent memory (investigations, playbooks). They used to write
    into `org_kettle`, the graph the app serves (FIX_LOG F-14). Before the first integration
    test, FalkorDB's GRAPH.COPY clones `org_kettle` to `org_kettle_pytest`; every GraphClient
    then opens the copy, and the copy is deleted at the end of the session.
    """
    wanted = any("integration" in item.keywords for item in request.session.items)
    if not wanted or not _falkordb_reachable():
        yield
        return

    import os

    from falkordb import FalkorDB

    from lore import db

    settings = get_settings()
    source, target = settings.graph_name, f"{settings.graph_name}_pytest"
    client = FalkorDB(
        host=settings.falkordb_host,
        port=settings.falkordb_port,
        password=settings.falkordb_password,
    )
    if target in client.list_graphs():
        client.select_graph(target).delete()
    if source in client.list_graphs():  # if nothing is loaded, the tests say so themselves
        client.select_graph(source).copy(target)

    previous = os.environ.get("LORE_GRAPH_NAME")
    os.environ["LORE_GRAPH_NAME"] = target
    get_settings.cache_clear()
    db._clients.clear()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("LORE_GRAPH_NAME", None)
        else:
            os.environ["LORE_GRAPH_NAME"] = previous
        get_settings.cache_clear()
        db._clients.clear()
        if target in client.list_graphs():
            client.select_graph(target).delete()


@pytest.fixture
def viewers() -> dict[str, Viewer]:
    """persona id -> Viewer for arjun, dana, sam, marco."""
    return {pid: viewer_for(pid) for pid in PERSONAS}


@pytest.fixture
def fake_graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def make_ctx(fake_graph, viewers):
    """Build a ToolContext: make_ctx("sam", mode="vector", now_ts=...)."""

    def build(persona: str = "arjun", **kwargs) -> ToolContext:
        return ToolContext(viewer=viewers[persona], graph=fake_graph, **kwargs)

    return build
