"""Graph data for the UI and the API: a neighbourhood, one source's text, the alert list.

Everything here is a thin wrapper around a query file in lore/queries/. Content nodes are
filtered by the viewer permission inside Cypher, so nothing hidden reaches the browser.
"""

from __future__ import annotations

from typing import Any

from lore.db import GraphLike, load_query
from lore.models import EdgeRef, GraphNode, GraphView
from lore.permissions import permission_params
from lore.tools import ToolContext

MAX_HOPS = 3  # more than this pulls in most of the company and is slow


def _node(id_: str, label: str, name: str | None, access: str | None, props: dict | None):
    return GraphNode(
        id=id_,
        label=label,
        name=name or id_,
        access_level=access,
        props={k: v for k, v in (props or {}).items() if v is not None},
    )


def neighbourhood(ctx: ToolContext, center: str, hops: int = 2, limit: int = 200) -> GraphView:
    """Nodes and edges within `hops` of `center` that the viewer may see (see the .cypher file)."""
    hops = max(1, min(int(hops), MAX_HOPS))
    # FalkorDB cannot take a path length as a parameter, so the (validated) number is pasted in.
    cypher = load_query("graph_neighbourhood").replace("__HOPS__", str(hops))
    params = {
        "center": center,
        "limit": max(1, min(int(limit), 1000)),
        **permission_params(ctx.viewer),
    }
    rows = ctx.graph.ro(cypher, params).dicts()

    nodes: dict[str, GraphNode] = {}
    links: list[EdgeRef] = []
    for r in rows:
        nodes.setdefault(
            r["a_id"], _node(r["a_id"], r["a_label"], r["a_name"], r["a_access"], r["a_props"])
        )
        nodes.setdefault(
            r["b_id"], _node(r["b_id"], r["b_label"], r["b_name"], r["b_access"], r["b_props"])
        )
        links.append(EdgeRef(source=r["a_id"], target=r["b_id"], type=r["rel"]))
    return GraphView(nodes=list(nodes.values()), links=links)


def source_detail(ctx: ToolContext, source_id: str) -> dict[str, Any] | None:
    """One source with its text, or None if it does not exist or the viewer may not see it."""
    cypher = load_query("source_detail")
    rows = ctx.graph.ro(cypher, {"id": source_id, **permission_params(ctx.viewer)}).dicts()
    if not rows or rows[0]["id"] is None:
        return None
    row = rows[0]
    chunks = [c for c in row.pop("chunks") if c]
    return {**row, "text": "\n\n".join(chunks)}


def list_alerts(graph: GraphLike) -> list[dict[str, Any]]:
    """Alerts the demo can investigate: [{id, name, symptom, service, started_at}]."""
    return graph.ro(load_query("list_alerts"), {}).dicts()


def alert_context(graph: GraphLike, alert_id: str) -> dict[str, Any] | None:
    """The alert, its failing service and tier, and when it started. None if unknown."""
    key = alert_id if alert_id.startswith("alert:") else f"alert:{alert_id}"
    rows = graph.ro(load_query("alert_context"), {"alert": key}).dicts()
    return rows[0] if rows else None
