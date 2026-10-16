"""Generate Kettle's synthetic data: `python -m lore.data_gen.generate`.

Reads the story bible constants (story.py), adds seeded filler (seed 20261015), and writes two
files to backend/data/. The output is byte-identical between runs (sorted, no timestamps).

  nodes.json  list of {"label": "PR", "id": "pr:482", "props": {...}}, sorted by (label, id)
  edges.json  list of {"type": "AUTHORED", "src": "person:priya", "dst": "pr:482", "props": {...}},
              sorted by (type, src, dst). src/dst are node ids; the loader finds their labels.

Every source node (PR, Thread, Ticket, Doc, Decision, Incident) has the access properties
`source, team, service, updated_at (unix seconds), access_level`, and restricted/confidential
ones have VISIBLE_TO edges (story-bible section 3). Chunks are NOT generated here: the loader
chunks and embeds text (lore/loader/).

Text: if backend/data/text/{threads,tickets,adrs,docs}.json exist (made once by
`python -m lore.data_gen.text_gen`) their text replaces the templates in templates.py. Planted
facts are re-checked, so a bad rewrite falls back to the template.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from lore.data_gen import story, templates
from lore.data_gen.story import IST, ist

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TEXT_FILES = {"thread": "threads", "ticket": "tickets", "adr": "adrs", "doc": "docs"}

SERVICE = {name: dict(tier=tier, team=team, deps=deps) for name, tier, team, deps in story.SERVICES}
PEOPLE = {
    slug: dict(name=name, team=team, title=title, joined=ist(joined), roles=roles)
    for slug, name, team, title, joined, roles in story.PEOPLE
}


def rng(name: str) -> random.Random:
    """A separate seeded generator per section, so adding code in one place never shifts others."""
    return random.Random(f"{story.SEED}:{name}")


def first(slug: str) -> str:
    return PEOPLE[slug]["name"].split()[0]


def day(ts: int) -> str:
    return datetime.fromtimestamp(ts, IST).strftime("%Y-%m-%d")


def rand_time(r: random.Random, lo: int, hi: int) -> int:
    """A weekday, between 10:00 and 19:00 IST, inside [lo, hi]."""
    while True:
        d = datetime.fromtimestamp(r.randint(lo, hi), IST).replace(hour=0, minute=0, second=0)
        if d.weekday() < 5:
            break
    t = int((d + timedelta(hours=10, minutes=r.randint(0, 540))).timestamp())
    return max(lo, min(t, hi))


def members_at(team: str, t: int) -> list[str]:
    """People who were in `team` at time t (Marco moves from pricing to data on 2026-08-01)."""
    out = []
    for slug, p in PEOPLE.items():
        current = p["team"]
        if slug == "marco":
            current = "pricing" if t < story.MARCO_MOVE else "data"
        if current == team and p["joined"] <= t:
            out.append(slug)
    return out


def employees_at(t: int) -> list[str]:
    return [s for s, p in PEOPLE.items() if "contractor" not in p["roles"] and p["joined"] <= t]


# ---------------------------------------------------------------- builder


@dataclass
class TextSlot:
    """One piece of text that Gemini may rewrite (used by text_gen.py)."""

    id: str
    kind: str  # thread | ticket | adr | doc
    context: str  # plain-English description for the prompt
    default: dict  # template text: {"title", "text", optional "summary"}
    required: list[str] = field(default_factory=list)  # facts that must appear in the new text


class Builder:
    def __init__(self, text_dir: Path | None):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}
        self.slots: list[TextSlot] = []
        self.overrides: dict[str, dict] = {}
        for filename in TEXT_FILES.values():
            path = text_dir / f"{filename}.json" if text_dir else None
            if path and path.exists():
                self.overrides.update(json.loads(path.read_text(encoding="utf-8")))

    def node(self, label: str, id: str, **props) -> None:
        assert id not in self.nodes, f"duplicate node id {id}"
        self.nodes[id] = {"label": label, "id": id, "props": props}

    def edge(self, type: str, src: str, dst: str, **props) -> None:
        self.edges[(type, src, dst)] = {"type": type, "src": src, "dst": dst, "props": props}

    def text(self, kind: str, id: str, context: str, default: dict, required=()) -> dict:
        """Planted text if the story has it, else saved Gemini text (if valid), else template."""
        planted = story.PLANTED_TEXT.get(id)
        required = list(planted["required"]) if planted else list(required)
        default = {k: v for k, v in (planted or default).items() if k != "required"}
        self.slots.append(TextSlot(id, kind, context, default, required))
        new = self.overrides.get(id)
        if (
            new
            and new.get("text")
            and all(
                f.lower() in (new.get("title", "") + " " + new["text"]).lower() for f in required
            )
        ):
            return {**default, **{k: v for k, v in new.items() if v}}
        return default

    def source(self, label, id, source, team, service, ts, level, **props) -> None:
        self.node(
            label,
            id,
            source=source,
            team=team,
            service=service,
            updated_at=ts,
            access_level=level,
            **props,
        )


# ---------------------------------------------------------------- organisation


def add_org(b: Builder) -> None:
    for t in story.TEAMS:
        b.node("Team", f"team:{t}", name=t.capitalize(), lead=f"person:{story.TEAM_LEADS[t]}")
    for role in story.ROLES:
        b.node("Role", f"role:{role}", name=role)
    for slug, private, _level, _visible in story.CHANNELS:
        b.node("Channel", f"channel:{slug}", name=f"#{slug}", private=private)
    for slug, p in PEOPLE.items():
        team = p["team"] or "none"
        employment = "contractor" if "contractor" in p["roles"] else "employee"
        b.node(
            "Person",
            f"person:{slug}",
            name=p["name"],
            title=p["title"],
            joined_at=p["joined"],
            employment=employment,
            team=team,
        )
        if p["team"]:
            since = story.MARCO_MOVE if slug == "marco" else p["joined"]
            b.edge("MEMBER_OF", f"person:{slug}", f"team:{p['team']}", since=since)
        for role in p["roles"]:
            b.edge("HAS_ROLE", f"person:{slug}", f"role:{role}")
        for channel in channels_for(slug):
            b.edge("IN_CHANNEL", f"person:{slug}", f"channel:{channel}")
    # Marco's history: no current path to #pricing-private
    b.edge(
        "WAS_MEMBER_OF",
        "person:marco",
        "team:pricing",
        **{"from": story.MARCO_PRICING_FROM, "to": story.MARCO_MOVE},
    )
    b.edge("WAS_IN_CHANNEL", "person:marco", "channel:pricing-private", to=story.MARCO_MOVE)


def channels_for(slug: str) -> list[str]:
    if slug in story.PERSONA_CHANNELS:
        return story.PERSONA_CHANNELS[slug]
    p = PEOPLE[slug]
    out = ["general", "eng", "incidents", p["team"]]
    if "oncall-engineer" in p["roles"] or "eng-manager" in p["roles"]:
        out.append("oncall")
    if slug in story.PRICING_PRIVATE_MEMBERS:
        out.append("pricing-private")
    return out


# ---------------------------------------------------------------- services


def add_services(b: Builder) -> dict[str, list[str]]:
    r = rng("modules")
    modules: dict[str, list[str]] = {}
    for name, tier, owner, deps in story.SERVICES:
        b.node("Service", f"svc:{name}", name=name, tier=tier, team=owner)
        b.node("Repo", f"repo:{name}", name=name)
        b.edge("OWNS", f"team:{owner}", f"svc:{name}")
        b.edge("BUILT_FROM", f"svc:{name}", f"repo:{name}")
        mods = story.FIXED_MODULES.get(name) or (
            ["config.yaml"] + sorted(r.sample(story.MODULE_POOL, r.randint(1, 3)))
        )
        modules[name] = mods
        for m in mods:
            b.node("CodeModule", f"mod:{name}/{m}", name=f"{name}/{m}", path=f"{name}/{m}")
            b.edge("CONTAINS", f"repo:{name}", f"mod:{name}/{m}")
        for dep in deps:
            b.edge("DEPENDS_ON", f"svc:{name}", f"svc:{dep}", w=1)
    return modules


# ---------------------------------------------------------------- PRs, tickets, deploys


def pick_author(r: random.Random, service: str, t: int) -> str:
    if service == "ledger":
        return "ines"  # bus factor 1
    team = SERVICE[service]["team"]
    pool = members_at(team, t)
    if team != "pricing" and r.random() < 0.1:  # a little cross-team work
        pool = employees_at(t)
    return r.choice(pool)


def pick_reviewer(r: random.Random, service: str, author: str, t: int) -> str:
    if service == "ledger":
        return "hana"
    pool = [p for p in members_at(SERVICE[service]["team"], t) if p != author]
    return r.choice(pool or members_at("platform", t))


def plan_prs(modules: dict[str, list[str]]) -> dict[int, dict]:
    """All 300 PRs as plain dicts: filler (seeded) + planted (story.STORY_PRS)."""
    r = rng("prs")
    slots = []
    for svc, n in story.FILLER_PRS_PER_SERVICE.items():
        count = n - 1 if svc == "pricing" else n  # PR #211 is planted
        for i in range(count):
            if svc == "pricing" and i < story.MARCO_PRICING_PRS:
                t, author = rand_time(r, story.DATA_START, story.MARCO_MOVE - 86400), "marco"
            else:
                t = rand_time(r, story.DATA_START, story.FILLER_END)
                author = pick_author(r, svc, t)
            slots.append(dict(service=svc, merged_at=t, author=author))
    slots.sort(key=lambda s: (s["merged_at"], s["service"]))
    lo, hi = story.FILLER_PR_NUMBER_RANGE
    pool = [n for n in range(lo, hi + 1) if n not in story.STORY_PRS]
    numbers = sorted(r.sample(pool, len(slots)))  # numbers grow with time
    prs: dict[int, dict] = {}
    for number, s in zip(numbers, slots, strict=True):
        s["reviewer"] = pick_reviewer(r, s["service"], s["author"], s["merged_at"])
        mods = r.sample(modules[s["service"]], r.randint(1, min(2, len(modules[s["service"]]))))
        s["mods"] = [(m, {}) for m in sorted(mods)]
        s["title"] = r.choice(templates.PR_TITLES).format(svc=s["service"], mod=mods[0])
        prs[number] = s
    for number, s in story.STORY_PRS.items():
        prs[number] = dict(s)
    return prs


def plan_tickets(prs: dict[int, dict]) -> dict[str, dict]:
    """80 tickets (79 filler + PRC-311). Done tickets get a filler PR that FIXES them."""
    r = rng("tickets")
    counts = {
        "checkout": 14,
        "pricing": 12,
        "dispatch": 13,
        "payments": 13,
        "data": 13,
        "platform": 14,
    }
    tickets: dict[str, dict] = {}
    for team in story.TEAMS:
        prefix = story.TICKET_PREFIX[team]
        owned = [n for n, s in SERVICE.items() if s["team"] == team]
        taken = {311} if prefix == "PRC" else set()
        for _ in range(counts[team]):
            num = r.choice([n for n in range(100, 421) if n not in taken])
            taken.add(num)
            created = rand_time(r, story.DATA_START, story.FILLER_END - 14 * 86400)
            status = r.choice(["open", "in_progress", "done", "done"])
            svc = r.choice(owned)
            tickets[f"{prefix}-{num}"] = dict(
                team=team,
                service=svc,
                created=created,
                status=status,
                updated=min(created + r.randint(1, 20) * 86400, story.FILLER_END),
                assignee=r.choice(members_at(team, created)),
            )
    tickets["PRC-311"] = dict(
        team="pricing",
        service="pricing",
        created=ist("2026-10-12 10:15"),
        status="done",
        updated=ist("2026-10-13 18:15"),
        assignee="priya",
    )
    # Link some done tickets to a later filler PR on the same service
    used: set[int] = set()
    for key in sorted(tickets):
        t = tickets[key]
        if t["status"] != "done" or key == "PRC-311":
            continue
        cands = [
            n
            for n, p in sorted(prs.items())
            if n not in story.STORY_PRS
            and n not in used
            and p["service"] == t["service"]
            and p["merged_at"] >= t["created"]
        ]
        if cands and r.random() < 0.8:
            n = r.choice(cands)
            used.add(n)
            prs[n]["fixes"] = f"ticket:{key}"
    return tickets


def plan_deploys(prs: dict[int, dict]) -> dict[int, dict]:
    """136 filler deploys (each ships 1+ PRs of one service) + the 4 planted ones."""
    r = rng("deploys")
    by_svc: dict[str, list[int]] = {}
    for n in sorted(prs, key=lambda n: prs[n]["merged_at"]):
        if n not in story.STORY_PRS or n == 211:
            by_svc.setdefault(prs[n]["service"], []).append(n)
    total = sum(len(v) for v in by_svc.values())
    want = {s: max(1, round(len(v) * story.FILLER_DEPLOYS / total)) for s, v in by_svc.items()}
    while sum(want.values()) != story.FILLER_DEPLOYS:  # nudge to the exact total
        step = 1 if sum(want.values()) < story.FILLER_DEPLOYS else -1
        cands = [
            s
            for s in by_svc
            if (step > 0 and want[s] < len(by_svc[s])) or (step < 0 and want[s] > 1)
        ]
        pick = max(cands, key=lambda s: (len(by_svc[s]) - want[s]) * step) if cands else None
        want[pick] += step
    raw = []
    for svc in sorted(by_svc):
        numbers = by_svc[svc]
        cuts = sorted(r.sample(range(1, len(numbers)), want[svc] - 1)) if len(numbers) > 1 else []
        for a, z in zip([0, *cuts], [*cuts, len(numbers)], strict=True):
            group = numbers[a:z]
            at = prs[group[-1]]["merged_at"] + r.randint(1800, 8 * 3600)
            raw.append((at, svc, group))
    raw.sort()
    deploys = {}
    for i, (at, svc, group) in enumerate(raw):
        deploys[story.FILLER_DEPLOY_FIRST_NUMBER + i] = dict(service=svc, at=at, prs=group)
    for number, (svc, at, group) in story.STORY_DEPLOYS.items():
        deploys[number] = dict(service=svc, at=at, prs=group)
    # versions grow with time within a service
    counter: dict[str, int] = {}
    for number in sorted(deploys, key=lambda n: deploys[n]["at"]):
        s = deploys[number]["service"]
        counter[s] = counter.get(s, 0) + 1
        deploys[number]["version"] = f"1.{counter[s] // 10 + 1}.{counter[s] % 10}"
    return deploys


def add_changes(b: Builder, prs, tickets, deploys) -> None:
    for key, t in sorted(tickets.items()):
        owner = t["team"]
        default = dict(zip(("title", "text"), _ticket_text(key, t), strict=True))
        txt = b.text(
            "ticket",
            f"ticket:{key}",
            f"Jira ticket {key}, {t['status']}, team {owner}, service {t['service']}.",
            default,
            [t["service"]],
        )
        b.source(
            "Ticket",
            f"ticket:{key}",
            "jira",
            owner,
            t["service"],
            t["updated"],
            "internal",
            key=key,
            name=key,
            title=txt["title"],
            text=txt["text"],
            status=t["status"],
            created_at=t["created"],
            assignee=f"person:{t['assignee']}",
        )
        b.edge(
            "MENTIONS", f"ticket:{key}", f"svc:{t['service']}", confidence=1.0, method="explicit"
        )
    for n, p in sorted(prs.items()):
        svc, team = p["service"], SERVICE[p["service"]]["team"]
        key = p.get("fixes", "").removeprefix("ticket:") or None
        text = p.get("text") or templates.pr_text(p["title"], svc, [m for m, _ in p["mods"]], key)
        b.source(
            "PR",
            f"pr:{n}",
            "github",
            team,
            svc,
            p["merged_at"],
            "internal",
            number=n,
            name=f"PR #{n}",
            title=p["title"],
            text=text,
            merged_at=p["merged_at"],
        )
        b.edge("AUTHORED", f"person:{p['author']}", f"pr:{n}")
        b.edge("REVIEWED", f"person:{p['reviewer']}", f"pr:{n}")
        b.edge("IN_REPO", f"pr:{n}", f"repo:{svc}")
        for mod, props in p["mods"]:
            b.edge("MODIFIES", f"pr:{n}", f"mod:{svc}/{mod}", **props)
        if "fixes" in p:
            b.edge("FIXES", f"pr:{n}", p["fixes"])
    for n, d in sorted(deploys.items()):
        b.node(
            "Deploy",
            f"deploy:{n}",
            number=n,
            name=f"deploy {n}",
            at=d["at"],
            version=d["version"],
            service=d["service"],
        )
        b.edge("DEPLOYED_TO", f"deploy:{n}", f"svc:{d['service']}")
        for pr in d["prs"]:
            b.edge("INCLUDES", f"deploy:{n}", f"pr:{pr}")


def _ticket_text(key: str, t: dict) -> tuple[str, str]:
    r = rng(f"ticket-text:{key}")
    svc2 = r.choice(SERVICE[t["service"]]["deps"] or ["config-service"])
    title = r.choice(templates.TICKET_TITLES).format(svc=t["service"], svc2=svc2)
    return title, templates.TICKET_TEXT.format(team=t["team"], svc=t["service"])


# ---------------------------------------------------------------- threads


def add_threads(b: Builder) -> None:
    """150 Slack threads, spread over the channels (story-bible section 8)."""
    r = rng("threads")
    all_svcs = [s[0] for s in story.SERVICES]
    for channel, _private, level, visible in story.CHANNELS:
        n = story.THREADS_PER_CHANNEL[channel]
        if channel in story.PRIVATE_THREAD_TIMES:
            numbered = {k: ist(v) for k, v in story.PRIVATE_THREAD_TIMES[channel].items()}
        else:
            times = sorted(rand_time(r, story.DATA_START, story.FILLER_END) for _ in range(n))
            if channel == "general":  # general-0003 is planted (an early public announcement)
                early = sorted(
                    rand_time(r, story.DATA_START, story.DATA_START + 4 * 86400) for _ in range(2)
                )
                planted_at = ist(story.PLANTED_THREADS["thread:general-0003"]["at"])
                rest = sorted(
                    rand_time(r, ist("2025-10-13"), story.FILLER_END) for _ in range(n - 3)
                )
                times = [*early, planted_at, *rest]
            numbered = {i + 1: t for i, t in enumerate(times)}
        team_of_channel = channel if channel in story.TEAMS else None
        for number, t in sorted(numbered.items()):
            tid = f"thread:{channel}-{number:04d}"
            plan = plan_thread(r, tid, channel, t, team_of_channel, all_svcs)
            add_thread(b, tid, channel, level, visible, plan)


def plan_thread(r, tid, channel, t, team_of_channel, all_svcs) -> dict:
    planted = story.PLANTED_THREADS.get(tid)
    if planted:
        return dict(
            at=t,
            author=planted["author"],
            services=planted["services"],
            people=planted["people"],
            template=None,
        )
    if channel == "hr-private":
        return dict(at=t, author="hr", services=[], people=[], template=None)
    if channel == "pricing-private":
        authors, pool = story.PRICING_PRIVATE_MEMBERS, story.PRICING_PRIVATE_MEMBERS
        svcs = ["pricing"]
    elif channel == "sec-incidents":
        authors, pool = ["dana", "amara"], ["dana", "amara"]
        svcs = [r.choice(["auth", "api-gateway", "user-profile"])]
    else:
        pool = members_at(team_of_channel, t) if team_of_channel else employees_at(t)
        if channel in ("incidents", "oncall"):
            pool = [s for s in employees_at(t) if "oncall-engineer" in PEOPLE[s]["roles"]]
        authors = pool
        home = [n for n, s in SERVICE.items() if s["team"] == team_of_channel]
        svcs = [r.choice(home or all_svcs)]
    want = r.choice([1, 1, 2, 2, 3])
    while len(svcs) < want:
        extra = r.choice(all_svcs)
        if extra not in svcs:
            svcs.append(extra)
    author = r.choice(authors)
    others = [p for p in pool if p != author]  # people who could plausibly be in the chat
    p1, who = r.sample(others, 2) if len(others) > 1 else (others[0], others[0])
    return dict(at=t, author=author, services=svcs, people=[p1, who], template=None)


def add_thread(b: Builder, tid, channel, level, visible, plan) -> None:
    r = rng(f"thread-text:{tid}")
    svcs, t = plan["services"], plan["at"]
    author = plan["author"]
    if plan["template"] is None and tid not in story.PLANTED_THREADS:
        if channel == "hr-private":
            fields = dict(a="HR", p1="HR", who="HR", svc="", svc2="")
        else:
            p1, who = plan["people"]
            fields = dict(
                a=first(author),
                p1=first(p1),
                who=first(who),
                svc=svcs[0],
                svc2=svcs[1] if len(svcs) > 1 else svcs[0],
            )
        title, body = templates.thread_text(r, channel, fields)
        default = dict(title=title, text=body)
    else:
        default = dict(title="", text="")
    speaker = "HR" if author == "hr" else first(author)
    context = (
        f"Slack thread in #{channel} on {day(t)}, started by {speaker}. "
        f"About the services: {', '.join(svcs) or 'none'}. "
        "2-5 short chat messages, each line 'FirstName: message'."
    )
    txt = b.text("thread", tid, context, default, svcs[:1])
    # Explicit MENTIONS: only what the final text really contains (at least the home service)
    body = "\n".join(line.split(": ", 1)[-1] for line in txt["text"].splitlines()).lower()
    mentioned_svcs = [s for s in svcs if s in txt["text"].lower()] or svcs[:1]
    team_ = SERVICE[svcs[0]]["team"] if svcs else "none"
    if channel in story.TEAMS:
        team_ = channel
    elif channel == "pricing-private":
        team_ = "pricing"
    elif channel == "sec-incidents":
        team_ = "platform"
    b.source(
        "Thread",
        tid,
        "slack",
        team_,
        svcs[0] if svcs else "none",
        t,
        level,
        channel=channel,
        name=tid.split(":")[1],
        title=txt["title"],
        text=txt["text"],
        author=f"person:{author}" if author != "hr" else "role:hr",
    )
    b.edge("POSTED_IN", tid, f"channel:{channel}")
    for target in visible:
        b.edge("VISIBLE_TO", tid, target)
    for s in mentioned_svcs if svcs else []:
        b.edge("MENTIONS", tid, f"svc:{s}", confidence=1.0, method="explicit")
    for p in plan["people"]:
        planted = tid in story.PLANTED_THREADS
        if planted or first(p).lower() in body:
            b.edge("MENTIONS", tid, f"person:{p}", confidence=1.0, method="explicit")


# ---------------------------------------------------------------- ADRs, docs, incidents, alerts


def add_decisions(b: Builder, prs) -> None:
    r = rng("adrs")
    for n, date, title, svc, author in story.ADRS:
        key = f"adr:{n:03d}"
        t = ist(date)
        default = templates.adr_text(n, date, title, svc, PEOPLE[author]["name"])
        txt = b.text(
            "adr",
            key,
            f"ADR-{n:03d} for the {svc} service, dated {date}, by "
            f"{PEOPLE[author]['name']}. Title: {title}.",
            default,
            [],
        )
        b.source(
            "Decision",
            key,
            "adr",
            SERVICE[svc]["team"],
            svc,
            t,
            "internal",
            number=n,
            name=f"ADR-{n:03d}",
            title=txt["title"],
            summary=txt["summary"],
            text=txt["text"],
            date=date,
            status="accepted",
        )
        b.edge("AUTHORED", f"person:{author}", key)
        b.edge("MENTIONS", key, f"svc:{svc}", confidence=1.0, method="explicit")
        if n == 11:
            continue
        later = [
            p
            for p, v in sorted(prs.items())
            if v["service"] == svc and v["merged_at"] > t and p not in story.STORY_PRS
        ]
        if later and r.random() < 0.7:
            b.edge("IMPLEMENTS", f"pr:{r.choice(later)}", key)
    b.edge("DISCUSSED_IN", "adr:011", "thread:pricing-private-0142")


def add_docs_and_incidents(b: Builder, prs) -> None:
    r = rng("docs")
    docs = [
        ("wiki:pricing-cache", "wiki", "pricing", "2025-06-01"),
        ("runbook:pricing-oncall", "runbook", "pricing", "2025-11-20"),
        *story.EXTRA_DOCS,
    ]
    for key, kind, svc, date in docs:
        team = SERVICE[svc]["team"]
        if kind == "wiki":
            default = templates.wiki_text(key, svc)
        else:
            default = templates.runbook_text(key, svc, team, PEOPLE[story.TEAM_LEADS[team]]["name"])
        txt = b.text(
            "doc",
            key,
            f"Internal {kind} page '{key}' about the {svc} service, last updated {date}.",
            default,
            [],
        )
        b.source(
            "Doc",
            key,
            kind,
            team,
            svc,
            ist(date),
            "internal",
            kind=kind,
            name=key,
            title=txt["title"],
            summary=txt.get("summary", ""),
            text=txt["text"],
            date=date,
        )
        b.edge("MENTIONS", key, f"svc:{svc}", confidence=1.0, method="explicit")
    b.edge("SUPERSEDES", "adr:011", "wiki:pricing-cache")

    for key, start, sev, title, svcs, resolver in story.INCIDENTS:
        level = story.INCIDENT_ACCESS.get(key, "internal")
        visible = ["role:security"] if level == "confidential" else []
        started = ist(start)
        resolved = started + r.randint(1, 4) * 3600
        team = SERVICE[svcs[0]]["team"]
        iid, pm = f"inc:{key}", f"pm:{key}"
        planted = story.PLANTED_TEXT.get(pm)
        names = PEOPLE[resolver]["name"]
        itext = templates.incident_text(title, sev, svcs, names)
        if key == "INC-0307":
            itext = (
                "Pricing overload after cache TTL lowered to 30s. PR #211 lowered the pricing "
                "cache TTL from 300s to 30s. Vendor API calls tripled, pricing latency rose "
                "and checkout slowed. Marco reverted PR #211 and restored 300s (see ADR-011)."
            )
        elif key == "INC-0326":
            itext = (
                "Leaked payments API key in a public gist. Key revoked and rotated. "
                "Discussed in #sec-incidents. Confidential."
            )
        b.source(
            "Incident",
            iid,
            "incident",
            team,
            svcs[0],
            resolved,
            level,
            key=key,
            name=key,
            title=title,
            symptom=title,
            severity=sev,
            started_at=started,
            resolved_at=resolved,
            text=itext,
        )
        pmd = planted or templates.postmortem_text(key, title, sev, svcs, names)
        txt = b.text("doc", pm, f"Postmortem for incident {key} ({title}).", pmd, [])
        b.source(
            "Doc",
            pm,
            "postmortem",
            team,
            svcs[0],
            started + 2 * 86400,
            level,
            kind="postmortem",
            name=pm,
            title=txt["title"],
            summary=txt.get("summary", ""),
            text=txt["text"],
            date=day(started + 2 * 86400),
        )
        b.edge("RECORDED_IN", iid, pm)
        b.edge("RESOLVED_BY", iid, f"person:{resolver}")
        for s in svcs:
            b.edge("AFFECTED", iid, f"svc:{s}")
            b.edge("MENTIONS", iid, f"svc:{s}", confidence=1.0, method="explicit")
        for target in visible:
            b.edge("VISIBLE_TO", iid, target)
            b.edge("VISIBLE_TO", pm, target)
        cause = story.INCIDENT_CAUSE_PR.get(key)
        if cause is None and key != "INC-0326":
            before = [
                n
                for n, p in sorted(prs.items())
                if p["service"] == svcs[0]
                and started - 14 * 86400 <= p["merged_at"] < started
                and n not in story.STORY_PRS
            ]
            cause = before[-1] if before else None
        if cause:
            b.edge("CAUSED_BY", iid, f"pr:{cause}")
    b.edge("DISCUSSED_IN", "inc:INC-0326", "thread:sec-incidents-0007")
    b.edge("MENTIONS", "inc:INC-0307", "adr:011", confidence=1.0, method="explicit")
    b.edge("MENTIONS", "pm:INC-0307", "adr:011", confidence=1.0, method="explicit")


def add_alerts(b: Builder) -> None:
    for key, a in story.STORY_ALERTS.items():
        b.node(
            "Alert",
            f"alert:{key}",
            key=key,
            name=key,
            symptom=a["symptom"],
            started_at=a["at"],
            service=a["service"],
        )
        b.edge("FIRED_ON", f"alert:{key}", f"svc:{a['service']}")


# ---------------------------------------------------------------- main


def build(text_dir: Path | None = DATA_DIR / "text") -> Builder:
    b = Builder(text_dir)
    add_org(b)
    modules = add_services(b)
    prs = plan_prs(modules)
    tickets = plan_tickets(prs)
    deploys = plan_deploys(prs)
    add_changes(b, prs, tickets, deploys)
    add_threads(b)
    add_decisions(b, prs)
    add_docs_and_incidents(b, prs)
    add_alerts(b)
    return b


def text_slots() -> list[TextSlot]:
    """Every text a human/Gemini could write (templates only). Used by text_gen.py."""
    return build(text_dir=None).slots


def dump(items: list[dict]) -> str:
    """One record per line so git diffs stay readable. Keys sorted, ASCII off, newline at end."""
    lines = (json.dumps(i, sort_keys=True, ensure_ascii=False) for i in items)
    return "[\n" + ",\n".join(lines) + "\n]\n"


def main(out_dir: Path = DATA_DIR) -> None:
    b = build(out_dir / "text")
    nodes = sorted(b.nodes.values(), key=lambda n: (n["label"], n["id"]))
    edges = sorted(b.edges.values(), key=lambda e: (e["type"], e["src"], e["dst"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nodes.json").write_text(dump(nodes), encoding="utf-8")
    (out_dir / "edges.json").write_text(dump(edges), encoding="utf-8")
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n["label"]] = counts.get(n["label"], 0) + 1
    print(f"wrote {len(nodes)} nodes and {len(edges)} edges to {out_dir}")
    print(", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
