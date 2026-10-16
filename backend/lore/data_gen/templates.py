"""Deterministic filler text used when backend/data/text/*.json (Gemini text) is absent.

Plain string templates, picked with a seeded `random.Random`. The wording is bland on purpose:
it must never contradict the planted stories (no talk of cache TTLs, no 'page <person>' advice
except the team lead).
"""

from __future__ import annotations

import random

# ---------------------------------------------------------------- Slack threads
# Each thread = (title, [messages]). {a} is the author, {p1} a second speaker,
# {svc}/{svc2} are service names, and {who} is an optional person to ping.

ENG_THREADS = [
    (
        "Flaky test in {svc}",
        [
            "{a}: The integration tests for the {svc} service failed twice on main "
            "today. Anyone else?",
            "{p1}: Yes, it is the timeout in the client mock. I will push a fix after lunch.",
            "{a}: Thanks. I will rerun the pipeline in the meantime.",
        ],
    ),
    (
        "Review request for {svc}",
        [
            "{a}: Could someone review my change to the {svc} service? It is small, "
            "about 40 lines.",
            "{p1}: On it. {who}, can you take a second look at the error handling?",
            "{a}: Thanks both, I will merge once CI is green.",
        ],
    ),
    (
        "Load test results for {svc}",
        [
            "{a}: Ran the load test against the {svc} service. p95 stayed under 250ms "
            "at 2x traffic.",
            "{p1}: Nice. Did you also test with {svc2} slowed down?",
            "{a}: Not yet. I will add that case and post the numbers here.",
        ],
    ),
    (
        "Question about {svc} and {svc2}",
        [
            "{a}: Does the {svc} service call {svc2} synchronously? I want to know before I change "
            "a timeout.",
            "{p1}: Yes, it is a blocking call with a 2s timeout. {who} knows the details.",
            "{a}: Perfect, that answers it.",
        ],
    ),
    (
        "Planning the next sprint for {svc}",
        [
            "{a}: Proposal for next sprint on the {svc} service: tidy the alerts, add "
            "two dashboards, "
            "and upgrade the runtime.",
            "{p1}: Sounds good. Can we leave room for support tickets?",
            "{a}: Yes, I will keep 20 percent free.",
        ],
    ),
    (
        "Dependency upgrade in {svc}",
        [
            "{a}: I am upgrading the base image for the {svc} service this week.",
            "{p1}: Remember to check the {svc2} client, it pins an older library.",
            "{a}: Good catch. I will test both together in staging.",
        ],
    ),
    (
        "Dashboard clean-up",
        [
            "{a}: The {svc} service dashboard has too many panels nobody looks at. I "
            "plan to remove "
            "half of them.",
            "{p1}: Please keep the error-rate and latency panels. The rest is fine to drop.",
        ],
    ),
]

GENERAL_THREADS = [
    (
        "Welcome to the new joiners",
        [
            "{a}: Please welcome the new joiners this month! Say hi and share a favourite tool.",
            "{p1}: Welcome! The {svc} service team is happy to pair if you want a code tour.",
        ],
    ),
    (
        "Shout-out to the {svc} team",
        [
            "{a}: Big shout-out to the {svc} service team for a smooth release last week.",
            "{p1}: Thanks! Special thanks to everyone who tested early.",
        ],
    ),
    (
        "Office hours and holidays",
        [
            "{a}: Reminder that the office closes early on Friday. Remote folks, nothing changes.",
            "{p1}: Thanks for the heads-up. The {svc} service on-call rota is unchanged.",
        ],
    ),
    (
        "Tech talk on the {svc} service",
        [
            "{a}: We are hosting a short tech talk about how the {svc} service handles peak dinner "
            "traffic. All welcome.",
            "{p1}: I will join. Will it be recorded?",
            "{a}: Yes, the recording goes in the wiki.",
        ],
    ),
    (
        "Book club",
        [
            "{a}: The engineering book club picks its next book on Thursday. Suggestions welcome.",
            "{p1}: Anything about the {svc} service architecture would be a bit too on the nose.",
        ],
    ),
]

INCIDENT_THREADS = [
    (
        "Elevated errors in {svc}",
        [
            "{a}: Seeing elevated 5xx on the {svc} service for a few minutes. Looking now.",
            "{p1}: I see it too. Rolled back the last config change, errors are dropping.",
            "{a}: Marking this resolved. I will open a follow-up ticket.",
        ],
    ),
    (
        "Slow responses from {svc}",
        [
            "{a}: p99 latency on the {svc} service doubled around 14:00.",
            "{p1}: A noisy neighbour on the same node. Moving the pod.",
            "{a}: Latency is back to normal. Thanks.",
        ],
    ),
    (
        "Incident review for {svc}",
        [
            "{a}: Writing the postmortem for the {svc} service incident now. Please add timeline "
            "details in the doc.",
            "{p1}: Added the deploy timestamps and the rollback steps.",
        ],
    ),
    (
        "{svc} alert noise",
        [
            "{a}: The {svc} service paged twice overnight for the same flapping check.",
            "{p1}: I will raise the threshold and add a two-minute delay before paging.",
        ],
    ),
]

ONCALL_THREADS = [
    (
        "On-call handoff",
        [
            "{a}: Handing over on-call. Quiet week. One noisy alert on the {svc} service that I "
            "silenced for 24 hours.",
            "{p1}: Thanks, got it. I will look at the alert threshold on Monday.",
        ],
    ),
    (
        "Pager test",
        [
            "{a}: Running the monthly pager test now. If you get a page that says "
            "'test', ignore it.",
            "{p1}: Received. The {svc} service escalation also works.",
        ],
    ),
    (
        "Who covers on-call over the holiday?",
        [
            "{a}: We need cover for the {svc} service on-call over the holiday weekend.",
            "{p1}: I can take Saturday. Anyone for Sunday?",
            "{a}: I will take Sunday.",
        ],
    ),
]

HR_THREADS = [
    (
        "Benefits enrolment reminder",
        [
            "HR: Reminder: benefits enrolment closes at the end of the month. Please "
            "review your plan.",
        ],
    ),
    (
        "Open headcount",
        [
            "HR: Headcount for next quarter was approved. Interview panels are being scheduled.",
        ],
    ),
    (
        "Performance review calendar",
        [
            "HR: The review calendar for the next cycle is published. Managers, please block time.",
        ],
    ),
]

PRICING_PRIVATE_THREADS = [
    (
        "Promo experiment rollout plan",
        [
            "{a}: Plan for the weekend promo experiment on the {svc} service: 10 "
            "percent of users first, then 50 percent.",
            "{p1}: Fine by me. {who}, can you watch the dashboards on Saturday?",
        ],
    ),
    (
        "Pricing roadmap sync notes",
        [
            "{a}: Notes from the roadmap sync for the {svc} service: tuning first, then "
            "promo stacking rules.",
            "{p1}: Added the open questions to the planning doc.",
        ],
    ),
    (
        "Pricing on-call rota",
        [
            "{a}: Updated rota for the {svc} service on-call. Please check your dates.",
            "{p1}: Swapped my Wednesday with {who}.",
        ],
    ),
]

SEC_THREADS = [
    (
        "Quarterly access review",
        [
            "{a}: Starting the quarterly access review, beginning with the {svc} "
            "service. Please confirm your team's channel members.",
            "{p1}: Confirmed for platform. Two contractors have expired accounts to remove.",
        ],
    ),
    (
        "Dependency vulnerability scan",
        [
            "{a}: The weekly scan found two medium-severity findings in the {svc} "
            "service. Tickets are filed.",
        ],
    ),
]

THREADS_BY_CHANNEL = {
    "general": GENERAL_THREADS,
    "incidents": INCIDENT_THREADS,
    "oncall": ONCALL_THREADS,
    "hr-private": HR_THREADS,
    "pricing-private": PRICING_PRIVATE_THREADS,
    "sec-incidents": SEC_THREADS,
}


def thread_text(rng: random.Random, channel: str, fields: dict) -> tuple[str, str]:
    """Pick a template for the channel and fill it. `fields` has a, p1, who, svc, svc2."""
    pool = THREADS_BY_CHANNEL.get(channel, ENG_THREADS)
    title, messages = rng.choice(pool)
    return title.format(**fields), "\n".join(m.format(**fields) for m in messages)


# ---------------------------------------------------------------- PRs

PR_TITLES = [
    "Fix flaky test in {mod}",
    "Refactor error handling in {mod}",
    "Add metrics to the {svc} service",
    "Bump dependencies for {svc}",
    "Handle timeouts in the {svc} client",
    "Add retry with backoff to {svc}",
    "Improve logging in {mod}",
    "Update {svc} README and examples",
    "Remove unused code from {mod}",
    "Validate input in {mod}",
    "Add unit tests for {mod}",
]


def pr_text(title: str, svc: str, mods: list[str], ticket_key: str | None) -> str:
    text = f"{title}. Touches {', '.join(mods)} in the {svc} service. Tested in staging."
    return text + (f" Fixes {ticket_key}." if ticket_key else "")


# ---------------------------------------------------------------- tickets

TICKET_TITLES = [
    "{svc}: intermittent timeout when calling {svc2}",
    "Add dashboard for {svc} error budget",
    "Upgrade the {svc} runtime",
    "Document failure modes of the {svc} service",
    "{svc}: reduce p99 latency of the list endpoint",
    "Remove dead feature flags from {svc}",
    "Add an alert for {svc} saturation",
    "{svc}: improve error messages returned to clients",
]
TICKET_TEXT = (
    "Raised by the {team} team. The {svc} service needs this to keep the on-call load low. "
    "Acceptance: change is deployed and the related dashboard is updated."
)


# ---------------------------------------------------------------- ADRs and docs


def adr_text(number: int, date: str, title: str, svc: str, author: str) -> dict:
    summary = f"{title}."
    text = (
        f"ADR-{number:03d}: {title}.\nStatus: accepted. Date: {date}. Author: {author}.\n"
        f"Context: The {svc} service needed a clear, shared rule so teams stop re-debating it.\n"
        f"Decision: {title}.\n"
        "Consequences: New code follows the rule. Exceptions need a new ADR."
    )
    return {"title": f"ADR-{number:03d}: {title}", "summary": summary, "text": text}


def wiki_text(slug: str, svc: str) -> dict:
    name = slug.split(":")[1].replace("-", " ")
    return {
        "title": name.capitalize(),
        "summary": f"Wiki page about {name} for the {svc} service.",
        "text": f"{name.capitalize()}. This page explains how the {svc} service fits into Kettle: "
        "what it does, who owns it, and where to find its dashboards.",
    }


def runbook_text(slug: str, svc: str, team: str, lead_name: str) -> dict:
    return {
        "title": f"{team.capitalize()} on-call runbook",
        "summary": f"On-call steps for the {svc} service.",
        "text": f"{team.capitalize()} on-call runbook. When the {svc} service alerts: "
        f"1. Check the dashboard. 2. Page {lead_name}, the {team} team lead. "
        "3. Post an update in #incidents. 4. Roll back the last deploy if errors started "
        "right after it.",
    }


def postmortem_text(
    key: str, title: str, severity: str, services: list[str], resolver: str
) -> dict:
    svcs = ", ".join(services)
    return {
        "title": f"Postmortem {key}: {title}",
        "summary": f"{severity} incident: {title}.",
        "text": f"Postmortem {key}. Summary: {title}. Severity {severity}. Affected: {svcs}. "
        f"Resolved by {resolver}. Actions: add a regression test, tune the alert and update "
        "the runbook.",
    }


def incident_text(title: str, severity: str, services: list[str], resolver: str) -> str:
    return (
        f"{title}. Severity {severity}. Affected services: {', '.join(services)}. "
        f"Resolved by {resolver}."
    )
