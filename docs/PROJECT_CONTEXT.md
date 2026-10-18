# Lore: project context for agents and humans

> Read this first if you are an AI agent (or a human) picking up work on this repo.
> Then read `STATE.md` (what is done), `PENDING_TASKS.md` (what is next) and `HUMAN_REVIEW.md` (open questions for Ayan).
> The full product plan is `docs/plan.md`. The fake company is specified in `docs/story-bible.md`.

## 1. What Lore is (one paragraph)

Lore is a hackathon project for **Graph Hacks (WeMakeDevs × FalkorDB, Oct 15–18 2026 IST, solo, author: Ayan)**. It loads a fictional food-delivery company ("Kettle") into one **FalkorDB** graph: people, teams, services, PRs, deploys, Slack threads, tickets, design decisions (ADRs) and incidents, plus **who may see what**. When an alert fires, four **Gemini** agents (Triage → Historian → Investigator → Responder) walk the graph with read-only Cypher tools and produce a **root-cause report where every sentence cites a source the viewer is allowed to see**. A human approves any outward action (Slack post, GitHub issue). It also answers free-form questions ("Ask the brain") with the same permission rules, and remembers past investigations as playbooks.

## 2. Hard rules (do not break these)

1. **Hackathon rules:** FalkorDB is mandatory. Only synthetic or public data. Code is written Oct 15–18. AI-assistant use must be disclosed (README). The author must be able to explain every part. Projects that are pure AI slop get disqualified, so keep the code small and explainable.
2. **Permissions are enforced inside Cypher.** Every query that returns content includes the viewer filter. Content the viewer can't see never leaves FalkorDB.
3. **The viewer comes from the session, never from the model.** `viewer` and `open_levels` are merged into query params by `tools.run_query()` *after* the model's args.
4. **Agent tools are read-only** (`GraphClient.ro()` → `GRAPH.RO_QUERY`). Only three modules write: the loader, `memory.py` (Investigation/Step/Finding/Playbook/EXPERT_IN/Query trace) and `actions.py` (Action nodes).
5. **Facts are computed in code, and the model narrates.** Severity, blast radius, owners, expertise scores and conflict resolution live in Python and Cypher. Gemini picks tools and writes text with citations.
6. **Every claim cites node ids returned by tools in this run** (`report.validate_claims`).
7. **Nothing leaves the system without a human click.** Actions start as `proposed`. Rollbacks are always simulated.
8. **Smallest abstraction that fits:** no LangChain or LangGraph. A plain Python agent loop on Gemini function calling.
9. **FalkorDB 4.18 Cypher quirk:** never put the permission path pattern in a `WHERE` attached to a `WITH` that computes a new value, and never apply it to nodes from `startNode()`/`endNode()`. Add a pass-through `WITH` or use a `granted` id list (see `STATE.md` C-02). Test every new content query as Dana (restricted access) against a live FalkorDB (`make db-lite`), because the bug only fires when the pattern is evaluated.
10. **Offline mode:** `LORE_FAKE_EMBEDDINGS=true` must match how the graph was loaded (`make load-fake`).

## 3. Repo layout

```
.
├── README.md                     # six-question README skeleton (plan section 18)
├── docker-compose.yml            # falkordb + api, for local use only
├── Makefile                      # common commands (see RUNBOOK), incl. the aws-* targets
├── infra/                        # AWS deployment (see section 9 and infra/README.md)
│   ├── cfn/                      # network.yaml, registry.yaml, app.yaml, frontend.yaml (CloudFormation)
│   ├── deploy.sh                 # deploy / secrets / status / logs / rollback / destroy
│   ├── buildspec.yml             # CodeBuild recipe for the ARM64 API image
│   ├── iam/                      # the deploying user's IAM policy
│   └── README.md                 # beginner guide, cost, security
├── .env.example
├── docs/
│   ├── plan.md                   # the product plan (source of intent)
│   ├── story-bible.md            # the fake company; single source of truth for data + evals
│   ├── discovery-brief.md        # plan section 0 as a standalone page
│   ├── PROJECT_CONTEXT.md        # this file
│   ├── STATE.md                  # what's implemented, challenges, verification status
│   ├── PENDING_TASKS.md          # ordered backlog (P0/P1/P2)
│   ├── HUMAN_REVIEW.md           # decisions/inputs that need Ayan
│   ├── DECISIONS.md              # design decision log
│   ├── RUNBOOK.md                # how to operate Lore (local and AWS)
│   ├── INFRA_PLAN.md             # the agreed AWS plan (what and why)
│   ├── hackathon-context.md      # official rules
│   └── reference/                # offline FalkorDB docs (html is gitignored) + its generator
├── backend/
│   ├── pyproject.toml            # uv project, Python ≥ 3.12
│   ├── lore/
│   │   ├── config.py             # Settings (env prefix LORE_)
│   │   ├── models.py             # ALL shared data shapes (contract)
│   │   ├── db.py                 # FalkorDB client, ro()/write(), load_query()
│   │   ├── permissions.py        # personas, viewer_for(), permission_params()
│   │   ├── tools.py              # tool registry + the ~10 read-only tools
│   │   ├── queries/*.cypher      # every Cypher query, documented (submission requirement)
│   │   ├── retrieval.py          # hybrid retrieval: vector / full-text / graph-scoped
│   │   ├── rerank.py             # explainable rerank score
│   │   ├── policy.py             # severity rule, source rank, post-audience check, request policy
│   │   ├── report.py             # citation validator
│   │   ├── llm.py                # Gemini wrapper (tools, structured output, embeddings) + FakeLLM
│   │   ├── agents/               # base loop, 4 agents, supervisor
│   │   ├── memory.py             # Investigation/Step/Finding/Playbook/EXPERT_IN writes
│   │   ├── ask.py                # "Ask the brain" pipeline
│   │   ├── actions.py            # Action lifecycle + Slack webhook + GitHub issue
│   │   ├── observability.py      # JSON logs, token/cost accounting
│   │   ├── replay.py             # record / play back runs (Gemini-down fallback)
│   │   ├── api/                  # FastAPI app, routes, SSE, session
│   │   ├── mcp_server.py         # FastMCP wrapping tools.py
│   │   ├── data_gen/             # story-bible → backend/data/*.json (seeded)
│   │   └── loader/               # data/*.json → FalkorDB (MERGE + UNWIND), indexes, embeddings
│   ├── data/                     # generated JSON (committed, so the demo never changes)
│   ├── eval/                     # golden.jsonl + run.py → report.md
│   ├── replays/                  # recorded golden runs (*.jsonl, gitignored except samples)
│   └── tests/                    # pytest (unit tests run without FalkorDB; integration marked)
└── frontend/                     # React + Vite + TS + Tailwind + react-force-graph-2d
```

## 4. Graph model (summary; full detail in plan section 5 and story-bible)

Nodes have a string `id` property (`person:arjun`, `svc:pricing`, `pr:482`, ...) and a `name` (display). Source nodes (`PR`, `Thread`, `Ticket`, `Doc`, `Decision`, `Incident`) and `Chunk` carry `source`, `team`, `service`, `updated_at` (unix seconds) and `access_level` ∈ {public, internal, restricted, confidential}.

Relationships: `MEMBER_OF`, `WAS_MEMBER_OF{from,to}`, `OWNS`, `HAS_ROLE`, `IN_CHANNEL`, `WAS_IN_CHANNEL{to}`, `VISIBLE_TO`, `DEPENDS_ON{w}`, `BUILT_FROM`, `CONTAINS`, `AUTHORED`, `REVIEWED`, `MODIFIES`, `IN_REPO`, `DEPLOYED_TO`, `INCLUDES`, `FIXES`, `MENTIONS`, `POSTED_IN`, `IMPLEMENTS`, `DISCUSSED_IN`, `RECORDED_IN`, `SUPERSEDES`, `FIRED_ON`, `AFFECTED`, `CAUSED_BY`, `RESOLVED_BY`, `EXPERT_IN{score,valid_from,valid_to}`, `PART_OF`.

Memory nodes: `Investigation`, `Step`, `Finding`, `Playbook`, `Agent`, `Action`, `Query` (trace).

**The permission predicate** (inline in every content-returning query):

```cypher
MATCH (viewer:Person {id: $viewer})
...
WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)
```

Only *current* relationships grant access (`WAS_MEMBER_OF` and `WAS_IN_CHANNEL` do not).

## 5. Module contracts

The shared types are in `backend/lore/models.py`. Key signatures:

| Module | Public surface |
|---|---|
| `db` | `GraphClient.ro(cypher, params) -> QueryOutcome`, `.write(...)`, `load_query(name)`, `get_graph()`; `GraphLike` protocol for fakes |
| `permissions` | `PERSONAS`, `viewer_for(persona_id) -> Viewer`, `permission_params(viewer)` |
| `tools` | `ToolContext`, `ToolArgs`, `@tool(...)`, `REGISTRY`, `run_query(ctx, name, params)`, `call_tool(ctx, name, raw_args) -> ToolResult` (never raises), `tools_for(names, mode)`, `embed_query(text)` / `set_embedder(fn)` (tools are sync; query embeddings go through this hook). `retrieval`, `rerank`, `actions` are imported lazily inside tool functions to avoid an import cycle with `llm` |
| `retrieval` | `vector_search(ctx, qvec, k)`, `fulltext_search(ctx, text, k)`, `graph_scoped_search(ctx, service, qvec, k)` → `list[Candidate]` (all permission-filtered); `restricted_match_count(ctx, qvec)` |
| `rerank` | `rerank(candidates, weights=DEFAULT_WEIGHTS, now_ts) -> list[Candidate]` with `0.5·meaning + 0.2·keyword + 0.2·graph + 0.1·recency` |
| `policy` | `severity_for(blast_radius_rows) -> "P1"/"P2"/"P3"`, `SOURCE_RANK`, `resolve_conflicts(sources) -> (winner, conflicts)`, `check_post_audience(graph, channel_id, cited_ids) -> PolicyDecision`, `check_request(text) -> PolicyDecision` |
| `report` | `validate_claims(claims, seen_ids) -> ValidationOutcome` |
| `llm` | `LLM` protocol: `async generate(model, system, contents, tools=None, response_schema=None) -> LLMResponse`, `async embed(texts, task) -> list[list[float]]`; `GeminiLLM`, `FakeLLM` (scripted, for tests/replay) |
| `agents.base` | `AgentSpec(name, model, system_prompt, tool_names)`, `async run_agent(spec, goal, ctx, llm, emit, blackboard) -> AgentOutput` |
| `agents.supervisor` | `async run_investigation(alert_id, viewer, *, mode, llm, graph, emit, settings=None) -> tuple[Report, RunSummary]` (fixed order, one retry if confidence < 0.7). It creates its own `inv:<uuid>` graph id; the API remaps event ids to its run id (`Run.graph_id` keeps the supervisor's) |
| `memory` | `start_investigation`, `record_step`, `record_finding`, `read_findings`, `save_playbook`, `find_playbooks`, `apply_feedback(graph, llm, investigation_id, confirmed, settings)`, `update_expertise`, `record_query_trace`. Writes are best-effort (logged, never crash a run) |
| `ask` | `async ask(question, viewer, *, mode, llm, graph) -> AskAnswer` |
| `actions` | `propose(...) -> Action`, `edit(id, text)`, `approve(id) -> Action` (runs policy, then sends), `reject(id)` |
| `replay` | `Recorder` (wraps emit, writes jsonl), `async play(path, emit, speed)` |
| `observability` | `log_event(**fields)` JSON logs, `estimate_cost(model, tokens_in, tokens_out)` |

`Emit = Callable[[StepEvent], Awaitable[None]]`. The Supervisor emits events, and the API pushes them to an `asyncio.Queue` per investigation that the SSE endpoint drains.

### Tools (~10 for the agents) and which agent uses them

| Tool | Query file | Agent | Modes |
|---|---|---|---|
| `find_entity(name)` | `find_entity.cypher` (full-text + exact id) | Triage | graph, vector |
| `blast_radius(service)` | `blast_radius.cypher` | Triage | graph |
| `service_criticality()` | `pagerank_services.cypher` | Triage | graph |
| `similar_incidents(symptom)` | `similar_incidents.cypher` (vector on Incident chunks, permission-filtered) | Historian | graph, vector |
| `get_playbook(symptom)` | `get_playbook.cypher` | Historian | graph |
| `search_discussions(query)` | `vector_search_permitted.cypher` | Historian | graph, vector |
| `recent_changes(service, hours)` | `recent_changes.cypher` | Investigator | graph |
| `evidence_path(alert_id, pr_number)` | `evidence_path.cypher` (`algo.SPpaths`) | Investigator | graph |
| `trace_decision(entity)` | `trace_decision.cypher` (Decision ← DISCUSSED_IN / SUPERSEDES / Incident RECORDED_IN) | Investigator | graph |
| `who_knows(service)` | `who_knows.cypher` | Responder | graph |
| `propose_action(kind, target, text, cited_ids)` | none (calls `actions.propose`) | Responder | graph, vector |

Graph OFF ("vector" mode) means the agents only get the tools marked `vector`. This is the baseline for the eval comparison.

## 6. HTTP API (FastAPI, prefix `/api`)

The session is a signed cookie `lore_session` holding `{persona}`. `POST /api/session` sets it. Every route resolves `viewer = viewer_for(session.persona)`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/health` | | `{status, falkordb: bool, gemini: bool, replay: bool}` |
| GET | `/api/personas` | | `Persona[]` |
| GET/POST | `/api/session` | POST `{persona: "arjun"}` | `{persona: Persona}` |
| GET | `/api/alerts` | | `[{id, name, symptom, service, started_at}]` (demo alerts A-3001, A-3002) |
| GET | `/api/graph` | `?center=svc:checkout&hops=2&limit=200` | `GraphView` (permission-filtered) |
| POST | `/api/investigations` | `{alert_id, mode: "graph"\|"vector", replay?: bool}` | `{investigation_id}` |
| GET | `/api/investigations/{id}/events` | SSE | stream of `StepEvent` (JSON in `data:`; SSE `event:` = `StepEvent.type`) |
| GET | `/api/investigations/{id}` | | `{report: Report\|null, summary: RunSummary, actions: Action[]}` |
| POST | `/api/investigations/{id}/feedback` | `{confirmed: bool, note?}` | `{playbook_id?}` |
| POST | `/api/ask` | `{question, mode}` | `AskAnswer` |
| PATCH | `/api/actions/{id}` | `{text}` | `Action` |
| POST | `/api/actions/{id}/approve` | | `Action` (may be `blocked` with reason) |
| POST | `/api/actions/{id}/reject` | | `Action` |
| GET | `/api/sources/{id}` | | `SourceRef` + text (permission-checked; 404 if not visible) |

### SSE `StepEvent.payload` by type

| type | payload |
|---|---|
| `investigation_started` | `{alert_id, viewer_id, mode, replay}` |
| `agent_started` / `agent_finished` | `{agent, goal}` / `{agent, confidence?, findings: n}` |
| `tool_call` | `{tool, reason, args}` (never contains viewer) |
| `tool_result` | `{tool, reason, cypher, ms, node_ids, edges, restricted_matches, row_count, error}` |
| `finding` | `{text, citations, confidence}` |
| `report` | `Report` |
| `action_proposed` | `Action` |
| `policy_blocked` | `{action_id?, reason}` |
| `error` | `{message, recoverable: bool}` |
| `done` | `RunSummary` |

## 7. Frontend

React + Vite + TS + Tailwind, `react-force-graph-2d`. Panels: persona switcher (top bar), alert list + "▶ Run the 3 AM incident" button, live graph canvas (highlights `node_ids`/`edges` from `tool_result` events, particles on active edges), reasoning trail (agent, reason, Cypher, ms; click to highlight), report card (claims with clickable citations, restricted-match warning, people to contact), actions panel (edit → approve/reject), run summary, Ask-the-brain tab, Graph ON/OFF toggle. The API base comes from `VITE_API_BASE`: unset means `http://localhost:8000`, and an empty value means same origin (the AWS build, where CloudFront serves the page and `/api/*` on one domain).

## 8. Environment

- Python 3.12+ with **uv** (`cd backend && uv sync`). Node 20+ (`cd frontend && npm install`).
- FalkorDB via Docker: `docker compose up falkordb` (port 6379). The image is `falkordb/falkordb-server:v4.18.3`, the same as on AWS (no Browser UI). **Docker is not installed on Ayan's Mac**; `make db-lite` is the substitute locally, and the AWS image is built in CodeBuild.
- Env vars use the prefix `LORE_` (see `.env.example`). Settings added for the AWS deployment:

| Setting | Default | Meaning |
|---|---|---|
| `LORE_COOKIE_SECURE` | `false` | Adds `Secure` to the session cookie. `true` on AWS (HTTPS only). The cookie is always `HttpOnly; SameSite=Lax` (page and API share one origin there). |
| `LORE_LOAD_ON_START` | `never` | `if_empty`: at startup, if the graph has no `Service` nodes (or no `Chunk` nodes), load `backend/data` in a background daemon thread with `load_on_start_*` log events. Never blocks startup or `/api/health`. Uses real embeddings unless `LORE_FAKE_EMBEDDINGS=true`; skipped (logged) with no Gemini key. |
| `LORE_CORS_ORIGINS` | `["http://localhost:5173"]` | `[]` on AWS (same origin, no CORS needed). |

- Rate limit key (`api/ratelimit.py`): `CloudFront-Viewer-Address` (port removed), else the first `X-Forwarded-For` entry, else the peer address. Trustworthy only because the ALB rejects requests lacking the secret `X-Origin-Verify` header.
- `GraphClient.write(cypher, params, timeout_ms=None)`: optional per-query timeout; the loader passes 30 s on its bulk writes.

## 9. Deployment architecture (AWS, ap-south-1)

Full plan: `docs/INFRA_PLAN.md`. Beginner guide: `infra/README.md`. Commands: `RUNBOOK.md` section 8.

```
Browser --HTTPS--> CloudFront (default dxxxx.cloudfront.net domain, no certificate)
   |-- /*      -> S3 bucket lore-web-<account> (React build, private, Origin Access Control)
   '-- /api/*  -> ALB lore-alb (HTTP :80; only CloudFront's IP list may connect; forwards only if header
                  X-Origin-Verify matches, else 403; idle timeout 300 s for SSE)
                    -> ECS Fargate task (ARM64, 1 vCPU / 2 GB, exactly one)
                         api container (uvicorn, 1 worker)  --localhost:6379, password-->  falkordb container
                                                                                              '-- EFS (encrypted, access point /falkordb)
```

- Four CloudFormation stacks: `lore-network`, `lore-registry`, `lore-app`, `lore-frontend` (`infra/cfn/`), deployed by `infra/deploy.sh`.
- The API image is built by CodeBuild (ARM64) from a zip of `backend/` and pushed to ECR `lore-api` (`:<git-sha>` and `:latest`).
- Secrets Manager: `lore/app` (5 keys, injected into the containers) and `lore/origin-verify` (CloudFront-to-ALB header value).
- Why this shape: D-14 (Fargate, not Lambda), D-15 (single task, FalkorDB sidecar, EFS), D-16 (default CloudFront domain, HTTP hop guarded by an IP list and a secret header).
