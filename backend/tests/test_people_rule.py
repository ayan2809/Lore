"""Who to contact is decided by code from the root cause (FIX_LOG F-03), not by the model."""

from __future__ import annotations

from lore.agents.supervisor import _people_by_rule
from lore.models import ToolResult


def _results():
    changes = ToolResult(
        tool="recent_changes",
        reason="",
        data=[
            {"service_id": "svc:checkout", "pr_id": "pr:479", "author_id": "person:leah"},
            {"service_id": "svc:pricing", "pr_id": "pr:482", "author_id": "person:priya"},
        ],
        node_ids=["svc:checkout", "pr:479", "person:leah", "svc:pricing", "pr:482", "person:priya"],
    )
    checkout_people = ToolResult(  # the Responder also asked about the alerted service
        tool="who_knows",
        reason="",
        data=[{"id": "person:meera", "role": "page"}],
        node_ids=["svc:checkout", "person:meera"],
    )
    pricing_people = ToolResult(
        tool="who_knows",
        reason="",
        data=[
            {"id": "person:rahul", "role": "page"},
            {"id": "person:marco", "role": "consult"},
            {"id": "person:priya", "role": "consult"},
            {"id": "person:nikhil", "role": "consult"},
        ],
        node_ids=["svc:pricing", "person:rahul", "person:marco", "person:priya", "person:nikhil"],
    )
    return [changes, checkout_people, pricing_people]


async def test_pages_the_owner_of_the_root_cause_service_not_the_alerted_one():
    people = await _people_by_rule("pr:482", ctx=None, emit=None, bb=None, all_results=_results())
    assert people.page == "person:rahul"
    assert people.consult == ["person:marco", "person:nikhil"]  # the author is notified instead
    assert people.notify == ["person:priya"]


async def test_no_rule_when_the_root_cause_is_not_a_deployed_change():
    assert await _people_by_rule(None, None, None, None, _results()) is None
    assert await _people_by_rule("adr:011", None, None, None, _results()) is None
