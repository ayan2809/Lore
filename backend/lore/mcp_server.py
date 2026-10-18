"""MCP server: the same read-only tools the agents use, for Gemini CLI and other MCP clients.

Run (stdio):   cd backend && uv run python -m lore.mcp_server

Who is asking? The persona comes from the environment variable LORE_MCP_PERSONA (arjun, dana,
sam or marco; default "sam" = least privilege). It is NEVER a tool argument, so an MCP client
(or the model behind it) cannot ask as someone else. Permission filters run inside the Cypher
queries exactly as in the web app.

Add it to Gemini CLI: edit ~/.gemini/settings.json

    {
      "mcpServers": {
        "lore": {
          "command": "uv",
          "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/Graph Hacks/backend",
                   "python", "-m", "lore.mcp_server"],
          "env": {
            "LORE_MCP_PERSONA": "arjun",
            "LORE_FALKORDB_HOST": "localhost",
            "LORE_GEMINI_API_KEY": "<only needed for the `ask` tool>"
          }
        }
      }
    }

stdout is the MCP protocol channel in stdio mode, so nothing in this module may print to it.
"""

from __future__ import annotations

import inspect
import os
import sys
from typing import Annotated, Any

try:  # mcp 2.x renamed FastMCP to MCPServer; mcp 1.x still has FastMCP
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

from pydantic import Field

from lore import tools
from lore.config import get_settings
from lore.permissions import PERSONAS, viewer_for

DEFAULT_PERSONA = "sam"


def viewer_from_env() -> Any:
    persona = os.environ.get("LORE_MCP_PERSONA", DEFAULT_PERSONA)
    if persona not in PERSONAS:
        print(f"unknown LORE_MCP_PERSONA {persona!r}, using {DEFAULT_PERSONA!r}", file=sys.stderr)
        persona = DEFAULT_PERSONA
    return viewer_for(persona)


def _graph():
    from lore import db

    return db.get_graph()


def make_tool_function(spec: tools.ToolSpec, viewer, graph_factory):
    """A function whose signature is the tool's args model (minus `reason`), so MCP clients see
    proper argument names, types and defaults."""
    fields = {n: f for n, f in spec.args_model.model_fields.items() if n != "reason"}
    params = [
        inspect.Parameter(
            name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Annotated[field.annotation, Field(description=field.description)],
            default=inspect.Parameter.empty if field.is_required() else field.default,
        )
        for name, field in fields.items()
    ]
    params.sort(key=lambda p: p.default is not inspect.Parameter.empty)  # required args first

    def run(**kwargs: Any) -> dict[str, Any]:
        ctx = tools.ToolContext(viewer=viewer, graph=graph_factory(), investigation_id="mcp")
        raw = {**kwargs, "reason": "Called through MCP"}
        return tools.call_tool(ctx, spec.name, raw).model_dump()

    run.__name__ = spec.name
    run.__doc__ = spec.description
    run.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    return run


# propose_action belongs to an investigation run and needs a human to approve it, so outside
# clients get the read-only tools only.
MCP_EXCLUDED_TOOLS = {"propose_action"}


def build_server(viewer=None, graph_factory=_graph) -> FastMCP:
    viewer = viewer or viewer_from_env()
    server = FastMCP("lore")
    for spec in list(tools.REGISTRY.values()):
        if spec.name in MCP_EXCLUDED_TOOLS:
            continue
        server.add_tool(
            make_tool_function(spec, viewer, graph_factory),
            name=spec.name,
            description=spec.description,
        )

    async def ask(question: str, mode: str = "graph") -> dict[str, Any]:
        """Ask the company brain a question. Answers cite sources the current persona may see."""
        settings = get_settings()
        if not settings.gemini_api_key:
            return {"error": "LORE_GEMINI_API_KEY is not set, so `ask` is unavailable."}
        from lore import ask as ask_module
        from lore import llm as llm_module

        answer = await ask_module.ask(
            question,
            viewer,
            mode="vector" if mode == "vector" else "graph",
            llm=llm_module.get_llm(settings),
            graph=graph_factory(),
        )
        return answer.model_dump()

    server.add_tool(ask, name="ask", description=ask.__doc__)
    return server


if __name__ == "__main__":
    build_server().run()  # stdio transport
