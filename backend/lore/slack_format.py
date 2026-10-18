"""Turn an approved incident report into a readable Slack message (HUMAN_REVIEW R-36).

Before: the model's free text, full of raw graph ids ("pr:482 ... person:rahul"), no structure.
Now: code builds a Slack Block Kit message from the structured Report (facts computed in code),
with human names, a header, sections and links. The only model-written part is the one-line
summary, which the human can edit before approving; ids in it are turned into names too.

Incoming webhooks accept `{"text": ..., "blocks": [...]}`; `text` is the notification fallback.
"""

from __future__ import annotations

import re
from typing import Any

from lore.db import GraphLike, load_query
from lore.models import Report

SEVERITY_EMOJI = {
    "P1": ":red_circle:",
    "P2": ":large_orange_circle:",
    "P3": ":large_yellow_circle:",
}
_ID = re.compile(r"\b[a-z]+:[A-Za-z0-9][\w./-]*")


def lookup_names(graph: GraphLike | None, ids: list[str]) -> dict[str, dict[str, Any]]:
    """{id: {label, name, title, number, symptom}} for the given ids (empty if no graph)."""
    if graph is None or not ids:
        return {}
    rows = graph.ro(load_query("slack_names"), {"ids": sorted(set(ids))}).dicts()
    return {r["id"]: r for r in rows}


def display(node_id: str, names: dict[str, dict[str, Any]], with_title: bool = False) -> str:
    """'pr:482' -> 'PR #482' (+ its title), 'person:priya' -> 'Priya Nair',
    'adr:011' -> 'ADR-011'."""
    n = names.get(node_id) or {}
    label = n.get("label")
    if label == "PR":
        text = f"PR #{n.get('number') or node_id.split(':', 1)[1]}"
    elif label == "Deploy":
        text = f"deploy {node_id.split(':', 1)[1]}"
    else:
        text = n.get("name") or n.get("title") or node_id.split(":", 1)[-1]
    title = n.get("title")
    if with_title and title and title != text:
        # "ADR-011: Pricing cache TTL..." already starts with the name: don't say it twice
        text = title if title.startswith(text) else f"{text} “{title}”"
    return text


def humanize(text: str, names: dict[str, dict[str, Any]]) -> str:
    """Replace known graph ids inside free text with their display names."""
    def swap(m: re.Match) -> str:
        return display(m.group(0), names) if m.group(0) in names else m.group(0)

    return _ID.sub(swap, text)


def _esc(text: str) -> str:
    """Slack mrkdwn needs &, < and > escaped."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(
    report: Report,
    alert_id: str,
    summary: str,
    names: dict[str, dict[str, Any]],
    *,
    lore_url: str | None = None,
    issue_url: str | None = None,
) -> dict[str, Any]:
    alert = names.get(alert_id if ":" in alert_id else f"alert:{alert_id}", {})
    alert_name = alert.get("name") or alert_id.split(":")[-1]
    symptom = alert.get("symptom") or "incident"
    severity = report.severity or "P?"
    path = report.evidence_path  # alert -> services ... -> deploy -> pr (code-computed)

    def people(ids: list[str]) -> str:
        return ", ".join(display(i, names) for i in ids) or "nobody"

    root = "not confirmed"
    if report.root_cause:
        root = f"*{_esc(display(report.root_cause, names, with_title=True))}*"
        if report.people.notify:
            root += f" by {_esc(people(report.people.notify))}"
        deploy = next((i for i in path if i.startswith("deploy:")), None)
        services = [i for i in path if i.startswith("svc:")]
        if deploy and services:
            service = _esc(display(services[-1], names))
            root += f"\ndeployed to *{service}* in {display(deploy, names)}"
    cited = [i for c in report.claims for i in c.citations]
    related = list(dict.fromkeys(i for i in cited if i.startswith(("adr:", "inc:"))))
    ruled_out = list(dict.fromkeys(c.citations[0] for c in report.rejected_suspects if c.citations))

    fields = [f"*Root cause*\n{root}"]
    if ruled_out:
        fields.append("*Ruled out*\n" + "\n".join(
            _esc(display(i, names, with_title=True)) for i in ruled_out))
    if related:
        fields.append("*Related decisions and incidents*\n" + "\n".join(
            _esc(display(i, names, with_title=True)) for i in related))
    page = f"*{_esc(display(report.people.page, names))}*" if report.people.page else "nobody"
    fields.append(
        f"*People*\nPage {page}\nConsult {_esc(people(report.people.consult))}\n"
        f"Notify {_esc(people(report.people.notify))}"
    )

    links = []
    if lore_url:
        links.append(f"<{lore_url}|Open Lore>")
    if issue_url:
        links.append(f"<{issue_url}|GitHub issue>")
    header = f"{severity} · {symptom}"[:150]  # Slack header limit
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": (
            f"{SEVERITY_EMOJI.get(severity, '')} Alert *{_esc(alert_name)}* · "
            f"confidence {round(report.confidence * 100)}% · from Lore, approved by a human")}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": _esc(humanize(summary, names))}},
        {"type": "section", "fields": [{"type": "mrkdwn", "text": f} for f in fields]},
    ]
    if links:
        link_text = {"type": "mrkdwn", "text": " · ".join(links)}
        blocks.append({"type": "context", "elements": [link_text]})
    fallback = f"{severity} {alert_name}: {humanize(summary, names)}"
    return {"text": fallback, "blocks": blocks}
