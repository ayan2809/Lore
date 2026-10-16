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
