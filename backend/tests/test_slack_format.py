"""Readable Slack/GitHub messages built from the report (HUMAN_REVIEW R-36)."""

from __future__ import annotations

import json

from lore import slack_format as fmt
from lore.models import Claim, PeopleToContact, Report

NAMES = {
    "alert:A-3001": {"label": "Alert", "name": "A-3001", "symptom": "checkout p99 latency > 3s"},
    "pr:482": {"label": "PR", "number": 482, "title": "Lower pricing cache TTL to 5s"},
    "pr:479": {"label": "PR", "number": 479, "title": "Update checkout button copy"},
    "deploy:991": {"label": "Deploy"},
    "svc:pricing": {"label": "Service", "name": "pricing"},
    "svc:checkout": {"label": "Service", "name": "checkout"},
    "adr:011": {"label": "Decision", "name": "ADR-011", "title": "ADR-011: Pricing cache TTL ok"},
    "inc:INC-0307": {"label": "Incident", "name": "INC-0307"},
    "person:rahul": {"label": "Person", "name": "Rahul Verma"},
    "person:marco": {"label": "Person", "name": "Marco Bianchi"},
    "person:priya": {"label": "Person", "name": "Priya Nair"},
}

REPORT = Report(
    summary="x",
    root_cause="pr:482",
    severity="P1",
    confidence=0.95,
    evidence_path=["alert:A-3001", "svc:checkout", "svc:pricing", "deploy:991", "pr:482"],
    claims=[Claim(text="breaks the ADR", citations=["pr:482", "adr:011", "inc:INC-0307"])],
    rejected_suspects=[Claim(text="copy only", citations=["pr:479"])],
    people=PeopleToContact(page="person:rahul", consult=["person:marco"], notify=["person:priya"]),
)


def test_message_uses_names_structure_and_links_not_raw_ids():
    summary = "Incident alert:A-3001: pr:482 lowered the TTL <see adr:011> & broke checkout."
    msg = fmt.build_message(REPORT, "alert:A-3001", summary, NAMES,
                            lore_url="https://d1.cloudfront.net",
                            issue_url="https://github.com/o/r/issues/2")
    text = json.dumps(msg["blocks"])
    assert msg["blocks"][0]["type"] == "header" and "P1" in msg["blocks"][0]["text"]["text"]
    assert "checkout p99 latency" in msg["blocks"][0]["text"]["text"]
    for raw in ("pr:482", "person:rahul", "adr:011", "inc:INC-0307", "deploy:991", "svc:pricing"):
        assert raw not in text, raw
    for readable in ("PR #482", "Priya Nair", "Rahul Verma", "Marco Bianchi", "ADR-011",
                     "INC-0307", "deploy 991", "PR #479"):
        assert readable in text, readable
    assert "<https://d1.cloudfront.net|Open Lore>" in text
    assert "<https://github.com/o/r/issues/2|GitHub issue>" in text
    assert "&lt;see ADR-011&gt; &amp; broke" in text  # mrkdwn escaping of the model's line
    assert "PR #482" in msg["text"]  # the notification fallback is readable too
    assert "ADR-011: Pricing cache TTL ok" in text and "ADR-011 “ADR-011" not in text


def test_unknown_ids_are_left_alone_and_missing_parts_are_skipped():
    bare = Report(summary="x", severity="P2")
    msg = fmt.build_message(bare, "A-9", "nothing about thread:secret-1", {}, lore_url=None)
    text = json.dumps(msg["blocks"])
    assert "thread:secret-1" in text  # not in the names map: not rewritten
    assert "Ruled out" not in text and "Open Lore" not in text
    assert "not confirmed" in text
