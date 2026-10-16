import asyncio

import pytest
from pydantic import Field

from lore import mcp_server, tools
from lore.models import ToolResult
from lore.permissions import viewer_for


class EchoArgs(tools.ToolArgs):
    service: str = Field(description="service id")
    hours: int = 24


def echo(ctx, args):
    return ToolResult(tool="echo", reason=args.reason, data=[{"viewer": ctx.viewer.id,
                                                              "service": args.service,
                                                              "hours": args.hours}])



@pytest.fixture(autouse=True)
def echo_tool(monkeypatch):
    monkeypatch.setitem(tools.REGISTRY, "echo", tools.ToolSpec("echo", "Echo args", EchoArgs, echo))


def call(server, name, args):
    return asyncio.run(server.call_tool(name, args))


def test_registry_tools_are_exposed_with_args_model_fields():
    server = mcp_server.build_server(viewer_for("arjun"), graph_factory=lambda: None)
    listed = asyncio.run(server.list_tools())
    names = {t.name for t in listed}
    assert {"echo", "ask"} <= names
    echo_tool = next(t for t in listed if t.name == "echo")
    props = echo_tool.input_schema["properties"]
    assert set(props) == {"service", "hours"}  # no `reason`, no `viewer`
    assert props["service"]["description"] == "service id"


def test_viewer_comes_from_server_not_args():
    server = mcp_server.build_server(viewer_for("sam"), graph_factory=lambda: None)
    result = call(server, "echo", {"service": "svc:pricing", "viewer": "person:dana"})
    text = str(result)
    assert "person:sam" in text and "person:dana" not in text


def test_persona_env_defaults_to_least_privilege(monkeypatch):
    monkeypatch.delenv("LORE_MCP_PERSONA", raising=False)
    assert mcp_server.viewer_from_env().id == "person:sam"
    monkeypatch.setenv("LORE_MCP_PERSONA", "dana")
    assert mcp_server.viewer_from_env().id == "person:dana"
    monkeypatch.setenv("LORE_MCP_PERSONA", "nobody")
    assert mcp_server.viewer_from_env().id == "person:sam"


@pytest.mark.parametrize("name", ["ask"])
def test_ask_without_key_returns_error(name, monkeypatch):
    no_key = type("S", (), {"gemini_api_key": None})()
    monkeypatch.setattr(mcp_server, "get_settings", lambda: no_key)
    server = mcp_server.build_server(viewer_for("sam"), graph_factory=lambda: None)
    assert "GEMINI_API_KEY" in str(call(server, name, {"question": "hi"}))
