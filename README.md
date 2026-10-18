# Lore: the company brain that already knows what broke

Lore loads a fictional food-delivery company ("Kettle") into one **FalkorDB** graph: people, teams, services, PRs, deploys, Slack threads, tickets, design decisions and incidents, plus **who may see what**. When an alert fires, four Gemini agents walk the graph with read-only Cypher tools and write a root-cause report where **every sentence cites a source the viewer is allowed to see**. A human approves anything that leaves the system.

Built solo by Ayan for **Graph Hacks** (WeMakeDevs x FalkorDB), Oct 15-18 2026.

> **Status: skeleton.** Items marked **TODO** are placeholders. Results, links and the video are filled in only when they exist. No number in this README is invented; evaluation numbers come from `backend/eval/report.md`.

Jump to: [Quickstart](#quickstart) | [Tracks](#tracks-entered) | [Live link and video](#live-link-and-video) | [AI-assistant disclosure](#ai-assistant-disclosure)

---

## 1. Who is the customer?

Kettle's engineering department: 45 engineers in 6 teams, about 30 microservices. The users are on-call engineers (many joined in the last 6 months), incident commanders, engineering managers and contractors with limited access. Kettle is fictional and all data is synthetic.

Full one-page brief: [docs/discovery-brief.md](docs/discovery-brief.md).

## 2. What was broken?

- It takes a median of **47 minutes** from alert to finding the cause of a serious (P1/P2) incident.
- **3 of the last 10** incidents paged the wrong person first.
- Knowledge is scattered (GitHub, Slack, Jira, ADRs, people's heads), partly restricted, and walks out of the door when people change teams.

## 3. What did you build?

Lore: a permission-aware company graph, four agents (Triage, Historian, Investigator, Responder), answers with sources, and actions behind human approval.

Success targets from the brief: time from alert to cause **under 3 minutes**, **0 permission leaks**, **at least 90%** of statements carrying a valid source, the right owner and expert named the first time. Whether it meets them is in [section 5](#5-how-did-you-evaluate-it).

What it does in the demo (details in [docs/plan.md](docs/plan.md) section 2):

- An alert fires and the agents' steps stream live while the graph lights up.
- A red herring is dismissed; the root cause comes with an evidence path and citations.
- The same question gets a different answer for different people (restricted sources are withheld).
- Lore names who to call; a human edits and approves the Slack post and GitHub issue.
- A post that would leak a restricted source is blocked by a check in code.
- Past investigations become playbooks the next run reuses.

## 4. How does it work?

### Architecture

![Lore architecture: browser, CloudFront and S3, FastAPI with a supervisor and four agents, read-only Cypher tools, FalkorDB, Gemini, Slack and GitHub behind human approval, and a local MCP server for Gemini CLI](docs/architecture.svg)

<details>
<summary>Text version</summary>

```
 Fake company data ("Kettle", a food-delivery startup)
 GitHub PRs · deploys · Slack (public + private channels) · Jira · ADRs · incidents
        │  MERGE loader + Gemini Flash extraction + embeddings + access metadata on every source
        ▼
 ┌────────────────────────── FalkorDB ───────────────────────────┐
 │ graph "org_kettle" = company brain + agent memory + access    │
 │ vector + full-text indexes · algorithms · permission paths    │
 └───────────────────────────────────────────────────────────────┘
        ▲  ~10 read-only Cypher tools, each filtered by the viewer's access
        │  Each returns: data + cypher + ms + node ids (permitted ones only)
        │
 FastAPI (viewer identity from session) ─ Supervisor ─► Triage → Historian → Investigator → Responder
    │  SSE: every step              policy checks in code │ proposals → human edits/approves → Slack, GitHub
    ▼                                                     ▼
 React UI: persona switcher · live graph · trail · cited report      MCP server (same tools) → Gemini CLI

 Eval harness: 50+ golden questions · leak tests · Graph ON vs OFF · latency and cost logs
```

</details>

Three rules carry the design:

1. **Every tool returns the part of the graph it touched** (node ids, the Cypher, the milliseconds). That powers the live animation, the audit trail and the explanation.
2. **Permissions are enforced inside the Cypher query.** Content the viewer may not see never leaves FalkorDB. The viewer comes from the login session, never from the model.
3. **Facts are computed in code; the model narrates.** Gemini picks tools and writes text; every claim must cite an id that a tool returned in this run.

### Who decides what

| The model (Gemini) does | The code does | A human does |
|---|---|---|
| Choose the next tool | Filter by permission inside every query | Approve Slack posts, GitHub issues and rollbacks |
| Read Slack, ticket and ADR text | Compute blast radius, paths, PageRank and expertise scores | Edit a proposed message before it goes out |
| Form and rank hypotheses | Set severity by rule (a tier-1 service in the blast radius means P1) | Confirm or reject the root cause, which feeds memory |
| Write the report and answers, with sources | Check every source link, and check that a post's audience may see every cited source | Request or grant access to restricted sources |
| Summarise an investigation into a playbook | Settle conflicts by source rank (ADR > runbook > ticket > Slack; newer beats older) | |

Deliberately not automated: rollbacks, paging real people, changing permissions, closing incidents, deciding severity.

### Graph data model

One graph per company (`org_kettle`); a second tenant such as `org_demo2` uses FalkorDB's multigraph feature. Every node has a string `id` (`person:arjun`, `svc:pricing`, `pr:482`, `adr:011`).

| Group | Nodes |
|---|---|
| Organisation | Person, Team, Role, Channel (`private: true/false`) |
| Code and services | Service (with `tier`), Repo, CodeModule, PR, Deploy |
| Knowledge | Ticket, Thread (Slack), Doc, Decision (ADR), Incident, Alert, Chunk (text + embedding) |
| Memory and trace | Investigation, Step, Finding, Playbook, Agent, Action, Query |

Main relationships:

- Organisation: `MEMBER_OF`, `OWNS`, `HAS_ROLE`, `IN_CHANNEL`. Leaving a team turns `MEMBER_OF` into `WAS_MEMBER_OF {from, to}`, so an access edge always means current access.
- Access: `VISIBLE_TO` (from a restricted source to the Team, Role or Channel allowed to see it).
- Services and code: `DEPENDS_ON`, `BUILT_FROM`, `CONTAINS`.
- Changes: `AUTHORED`, `REVIEWED`, `MODIFIES`, `IN_REPO`, `DEPLOYED_TO`, `INCLUDES`, `FIXES`.
- Discussions and decisions: `MENTIONS`, `POSTED_IN`, `IMPLEMENTS`, `DISCUSSED_IN`, `RECORDED_IN`, `SUPERSEDES`.
- Incidents: `FIRED_ON`, `AFFECTED`, `CAUSED_BY`, `RESOLVED_BY`.
- Learned: `EXPERT_IN {score, valid_from, valid_to}`, `PART_OF` (Chunk to its source).

Every source node and Chunk carries `source`, `team`, `service`, `updated_at` (Unix seconds) and `access_level`: `public`, `internal`, `restricted` or `confidential`.

**The permission rule.** A viewer can see a source if its access level is open to them, or if there is a *current* path viewer -> Team/Role/Channel <- `VISIBLE_TO` <- source. In Cypher, inside every content-returning query:

```cypher
MATCH (viewer:Person {id: $viewer})
...
WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)
```

Demo personas: Arjun (on-call engineer, sees public + internal + his own channels), Dana (incident commander with the security role), Sam (contractor, public only), Marco (moved from Pricing to Data, lost access to `#pricing-private`).

Full schema: [docs/plan.md](docs/plan.md) section 5, story: [docs/story-bible.md](docs/story-bible.md).

### Documented Cypher

Every query the system runs lives in its own documented file: **[backend/lore/queries/](backend/lore/queries/)** (`*.cypher`). TODO: confirm the folder is complete and each file has a header comment explaining what it does and why, once the backend is finished.

### Identity, retries and failures

- The session cookie holds only the persona. The server turns it into a `viewer` and merges it into the query parameters *after* the model's arguments, so the model cannot choose who it is.
- Agent tools use read-only queries (`GRAPH.RO_QUERY`). Only the loader and the memory module write.
- Model output is parsed into Pydantic models; bad output gets one retry with the error explained.
- Every claim is checked against the ids returned by tools in the run; uncited claims are retried once, then dropped and flagged.
- Slow tool calls time out and retry with backoff. If Gemini is down, replay mode plays back a recorded run.

### Failure cases

Failures are built in on purpose. The "what the system did" column is filled in from real runs; TODO until then.

| Failure | How it is caused | What Lore should do (design) | What the system did (TODO) |
|---|---|---|---|
| Out-of-date or conflicting source | Story D in the story bible | Rank sources by rule, answer from the most trustworthy, show both with a "conflict" tag | TODO |
| Model returns badly formatted output | Test that feeds broken output | Reject with Pydantic, retry once with the error, otherwise show raw findings with a warning | TODO |
| A tool call times out | Artificial delay on a query or the GitHub API | Give up after a set time, back off and retry, mark the step failed, continue with other evidence | TODO |
| User lacks permission | Sam asks about the security incident | Refuse with the restricted warning and who to ask; the trace shows nothing restricted was fetched | TODO |
| Request breaks policy | "Post the security details to #general", "Roll back prod now" | Block in code with the reason; a rollback is only ever a proposal | TODO |
| Gemini is down or out of quota | Revoke the API key during a test run | Replay mode, clearly labelled | TODO |

## 5. How did you evaluate it?

A fixed set of 50+ golden questions (`backend/eval/golden.jsonl`) across five types (easy lookup, cross-source synthesis, conflicting sources, out-of-date information, should refuse), asked as different personas. Each layer is measured separately. Scoring is deterministic (key facts and source ids present), not an AI judge. Run it with `make eval`; it writes `backend/eval/report.md`.

**TODO: fill this table from `backend/eval/report.md` after `make eval`. Do not type numbers that are not in the report.**

| Layer | Measure | Target | Graph ON | Graph OFF (vector only) |
|---|---|---|---|---|
| Retrieval | Expected sources in top 5 (recall); forbidden ids returned | High recall; 0 forbidden | TODO | TODO |
| Generation | Claims with a valid source | at least 90% | TODO | TODO |
| Generation | Key facts present (`must_include`) | TODO | TODO | TODO |
| Generation | Correct refusals on "should refuse" questions | all | TODO | TODO |
| Permissions | Restricted ids in any persona's results or citations | **0** (automatic pytest test) | TODO | TODO |
| Investigations | Root cause correct (5 runs x 3 scenarios), red herring rejected | TODO | TODO | TODO |
| Investigations | Time to root cause | under 3 min | TODO | TODO |
| Investigations | Steps and cost per run | TODO | TODO | TODO |

Hand-checked answers: TODO (about 10 checked by hand; record how many matched the automatic score).

## 6. What would you change before real production use?

- Real GitHub, Slack and Jira connections (webhooks, plus backfilling old data) instead of generated data.
- Single sign-on, with permissions copied from the source systems and re-checked regularly, instead of demo personas.
- Remove personal data before it enters the graph.
- Keep audit logs for a set time.
- Run the evals automatically on every change and block merges that add a leak.
- Cost budgets per team and per request.
- Run inside the customer's own private cloud network (VPC), so no data leaves it.

---

# Hackathon requirements

## Quickstart

Needs: [uv](https://docs.astral.sh/uv/), Node 20+, and Docker Desktop (for FalkorDB). A Gemini API key is optional: with `make load-fake` and replay mode you can run without one.

```bash
cp .env.example .env     # then edit it; add LORE_GEMINI_API_KEY if you have one
make setup               # uv sync + npm install
make db                  # FalkorDB in Docker: port 6379, FalkorDB Browser on http://localhost:3000
make gen                 # (optional) regenerate backend/data/*.json; the generated files are committed
make load-fake           # load the Kettle graph with fake embeddings (use `make load` for real ones)
make api                 # API on http://localhost:8000   (terminal 2)
make web                 # web page on http://localhost:5173   (terminal 3)
```

**UI only, no backend:** `make mock` runs the web page on fake data (`VITE_MOCK=1`).

Other commands: `make test` (fast tests), `make test-all`, `make lint`, `make eval`, `make mcp`. `make help` lists everything. Operating notes, deploy steps and troubleshooting: [docs/RUNBOOK.md](docs/RUNBOOK.md).

**No Docker?** `make db-lite` runs a real FalkorDB (the same module, via [FalkorDBLite](https://github.com/FalkorDB/falkordblite)) on port 6390 with no Docker and no Browser UI. Set `LORE_FALKORDB_PORT=6390` in `.env`. The Oct 16 skeleton was verified this way: loader, every tool, the leak tests and an end-to-end Story A run. FalkorDB Cloud also works in principle (set `LORE_FALKORDB_HOST/PORT/PASSWORD`); it is untested.

## Tracks entered

All three tracks.

- **Track 1, Agents that act on connected data:** agents move through service dependencies and code changes, use graph algorithms (PageRank, shortest paths) as tools, propose real actions behind human approval, and expose the same tools over MCP.
- **Track 2, Agent memory and coordination:** agents remember past investigations as episodic steps, expertise scores with validity dates, and learned playbooks, and share one working space inside the graph.
- **Track 3, Company brain:** people, teams, code, Slack, tickets and design decisions live in one graph, and answers cite their sources and respect permissions.

## Live link and video

- Live demo: **TODO** (frontend on Vercel, API on a VM; the link goes here, with the replay fallback noted).
- Demo video (about 3 minutes, business problem first, with one failure case): **TODO**
- Blog post: **TODO** (optional side prize)

## Project docs

| File | What |
|---|---|
| [docs/plan.md](docs/plan.md) | The product plan |
| [docs/discovery-brief.md](docs/discovery-brief.md) | The customer and the problem, one page |
| [docs/story-bible.md](docs/story-bible.md) | The fake company; single source for data and evals |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | How to run, reset, deploy and troubleshoot |
| [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | Repo layout, API and module contracts |

## AI-assistant disclosure

Hackathon rules require disclosing AI coding assistants. **This is an honest first draft. TODO(Ayan): review and rewrite it in your own words so it is exactly true.**

**Tool used:** Claude Code (Anthropic). On Oct 16 2026, Claude Code was used to scaffold the project skeleton: backend modules, frontend, Docker and CI configuration, the Makefile, the runbook and this README structure. Gemini is used at runtime by the product itself (agents, extraction, embeddings) and to generate the synthetic Slack/ticket/ADR wording.

**Planning (before Oct 15):** the plan (`docs/plan.md`) was drafted with Claude in planning sessions at Ayan's request: Ayan set the constraints (solo, Python + React + FalkorDB + FastAPI + Gemini, demoable in 4 days, FDE portfolio framing) and asked Claude to propose the project; Claude proposed the domain, the "Lore" concept, the discovery brief numbers, the permission model and the eval design; Ayan reviewed and re-shaped it (e.g. aligning it to the FDE handout's Project 1). TODO(Ayan): correct this paragraph so it states exactly what you decided yourself.

**During the hackathon:** the story bible (`docs/story-bible.md`) was drafted by Claude from the plan on Oct 16 and is under Ayan's review. TODO(Ayan): list here the design decisions you changed or own (the permission rules, the who-decides-what split, the eval design, the prompts).

**Generated by AI (Claude Code) and reviewed by Ayan:** TODO(Ayan): replace this line with the exact list once you have reviewed the code, for example which modules, tests and config files were AI-generated and how you checked them.

Ayan must be able to explain every part of the system (hackathon rule 12). TODO(Ayan): note here anything you could not yet explain and how you resolved it.
