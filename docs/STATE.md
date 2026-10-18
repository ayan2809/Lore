# Lore: implementation state

> **Last updated:** Oct 18 2026, after the first **live** local test round (real Gemini, real embeddings, real Slack/GitHub) and the AWS infra build. Branch `feature/aws-infra`. **Read §0 first**; §1–7 describe the Oct 16 skeleton.
> Read `PROJECT_CONTEXT.md` first for the architecture and contracts. This file says **what exists, how far it was verified, and what went wrong on the way**. `PENDING_TASKS.md` is the backlog; `HUMAN_REVIEW.md` lists what needs Ayan.

## 0. Oct 18 update: live local test round

Everything that was "never run live" on Oct 16 has now run live, locally (FalkorDB 4.18.3 via `make db-lite`, real `gemini-embedding-2` vectors). The test config is `gemini-3.5-flash-lite` for the light agents and `gemini-3.8-flash` for the Investigator. **14 fixes**, each with cause and verification, are in [FIX_LOG.md](FIX_LOG.md).

| Area | Status Oct 18 |
|---|---|
| `GeminiLLM` (tool calling, structured output, embeddings) | ✅ live |
| Story A (4 personas) / Story B (memory) | ✅ live; root cause correct every run; Story B 8 → 4 Investigator steps with the playbook |
| Ask the brain | ✅ live; graph facts added (F-06); 12/12 on the first golden questions |
| API + SSE + cookie session | ✅ live over HTTP |
| Real Slack post + GitHub issue | ✅ sent (issue #1 in `ayan2809/kettle-incidents`) |
| Frontend on the real API | ✅ headless Chrome; evidence path lights up; report renders; 0 console errors |
| Eval | Retrieval: Graph ON 75% vs OFF 38% recall@5. Generation: key facts 71% vs 43%, refusals correct 93% vs 66%. **0 leaks** |
| Replays | ✅ 5 real recordings committed (`backend/replays/story_*.jsonl`); playback verified |
| AWS infra (`infra/`) | ✅ **Deployed Oct 18 (14:25 IST): https://d1cu7fzoa0v5wz.cloudfront.net** (image `47cd1c81bb71`, ARM64). Verified live: health; first boot loaded the graph with real embeddings in 19 s; a full investigation streams through CloudFront (53 SSE events / 53 s); UI in headless Chrome; replay; cookie `HttpOnly; Secure; SameSite=Lax`; the ALB is unreachable directly; the graph survives a task restart (AOF on EFS, reload 0.8 s) |
| Tests | 304 unit + 23 integration = **327 pass** on the live graph |

New challenges (details in FIX_LOG):
- `gemini-embedding-2` merges a list of strings into one vector (F-02).
- The model chose who to page wrongly; that's now decided in code (F-03).
- Text-only Ask can't answer relationship questions (F-06).
- GitHub issues could cite restricted sources; now blocked (F-09).
- Playbooks didn't shorten runs until they were given a step budget (F-11).
- The eval duplicated retrieval logic and reported Graph ON < OFF (F-13).
- Integration tests write into the real graph (F-14, pending T-39).

## 1. Summary

The full skeleton exists and is **verified against a real FalkorDB engine** (FalkorDB 4.18.3, run locally through FalkorDBLite because Docker isn't installed). Everything except live Gemini has been exercised:

- **Loader:** 943 nodes, 2,854 edges and 579 chunks, with fake embeddings and no orphan nodes.
- **Every agent tool** returns the planted Story A facts, filtered correctly for each persona.
- **An end-to-end Story A run** goes through the real Supervisor, the four agents, the Cypher tools, memory writes and the citation validator. A scripted model stands in for Gemini.
- **The HTTP API** serves the permission-filtered graph view: a private source returns 404 for Arjun and Sam and 200 for Dana.

**Not yet exercised:**
- **Live Gemini:** no key is configured. Agent prompts, structured output, function calling and real embeddings have never run.
- **Docker, the AWS deployment and CI:** the AWS templates and `deploy.sh` are written and validated offline (below) but **never deployed**; Docker Compose and the Dockerfile have never been run.
- **The frontend against the real backend:** it has only run in mock mode.

## 2. Size

| Area | Files | Lines (approx.) |
|---|---|---|
| Backend `lore/` (Python) | 37 modules | 7,000 |
| Cypher `lore/queries/*.cypher` | 39 queries, each with a plain-English header | |
| Backend tests and eval harness | 18 test files + eval | 4,400 |
| Frontend `src/` (React + TS) | 21 files | 3,100 |
| Data `backend/data/*.json` | generated, committed | 560 KB |
| Golden questions `backend/eval/golden.jsonl` | 59 questions, 5 types, 4 personas | |

## 3. Module status

Legend: ✅ implemented and verified · 🟡 implemented, only unit-tested with fakes · ⚪ placeholder

| Module | Status | Verified how |
|---|---|---|
| `config`, `models`, `permissions`, `db` | ✅ | Live FalkorDB |
| `data_gen/generate.py` + `story.py` + `templates.py` | ✅ | Deterministic: byte-identical output; story invariants tested |
| `data_gen/text_gen.py` (Gemini Flash text, run once) | 🟡 | Mocked Gemini only; `--dry-run` works |
| `loader/` (indexes, MERGE+UNWIND, chunks, embeddings, MENTIONS extraction) | ✅ | Loaded into live FalkorDB (fake embeddings) |
| `queries/*.cypher` (tools, retrieval, view, policy, memory, ask, action) | ✅ mostly | Tool, view and memory queries ran live; `ask_*`, `action_upsert` and `post_audience_check` are only unit-tested |
| `tools.py` (11 agent tools; the `run_cypher` safety net was removed, FIX_LOG F-20) | ✅ | Live probe as arjun, dana and sam (see §4) |
| `retrieval.py`, `rerank.py` | ✅ / 🟡 | Live vector + full-text with fake vectors; rerank weights untuned |
| `policy.py` (severity, source rank, conflicts, post-audience, request policy) | 🟡 | Unit tests; severity verified in the e2e run |
| `report.py` (citation validator) | ✅ | e2e: an invented `pr:999` claim was dropped |
| `llm.py` (GeminiLLM + FakeLLM + tool declarations) | 🟡 | FakeLLM only; **GeminiLLM never called** |
| `agents/` (loop, 4 agents, supervisor) | ✅ with a scripted model | `tests/test_e2e_story_a.py` against live FalkorDB |
| `memory.py` (Investigation/Step/Finding/Playbook/feedback/EXPERT_IN/Query trace) | ✅ mostly | Live: Steps, Findings, Playbook save and recall; `update_expertise` and `record_query_trace` only unit-tested |
| `ask.py` ("Ask the brain") | 🟡 | Unit tests; the live API returns 503 without a Gemini key |
| `actions.py` (propose/edit/approve/reject, Slack, GitHub, simulated rollback) | 🟡 | Unit tests with mocked HTTP; no real webhook or token yet |
| `api/` (FastAPI, cookie session, SSE, rate limit, replay) | ✅ partly | Live: health, alerts, graph, sources per persona. SSE only with fakes |
| `replay.py` + `replays/sample_story_a.replay.json` | 🟡 | The sample is **hand-written**, not recorded |
| `mcp_server.py` | 🟡 | Import + unit test; **not tried in Gemini CLI** |
| `observability.py` | 🟡 | The `PRICES` table holds placeholder numbers |
| `eval/run.py` + `scoring.py` | 🟡 | Scoring unit-tested; no full run yet (needs Gemini for the generation layer) |
| `frontend/` | ✅ in mock mode | `npm run build` + oxlint clean; headless screenshots at 1080p and 1366×768 |
| Docker Compose, backend Dockerfile, CI | ⚪ | Written and YAML-validated; never run (no Docker on this Mac). Caddy and Vercel config were removed (D-14 to D-16) |
| `infra/` (AWS: 4 CloudFormation stacks, `deploy.sh`, `buildspec.yml`) | 🟡 | Oct 18, branch `feature/aws-infra`. `cfn-lint` clean; `aws cloudformation validate-template` OK for all four; `bash -n` + shellcheck clean; `deploy.sh secrets` and `backend-only` exercised against a stub `aws` (no secrets on the command line, correct params file, zip contents). **Nothing deployed; no AWS resource created.** Docs: `infra/README.md`, `RUNBOOK.md` §8–9 |
| Same-origin changes (`LORE_COOKIE_SECURE`, rate-limit IP from `CloudFront-Viewer-Address`, `LORE_LOAD_ON_START`, loader write timeout) | ✅ | Unit tests; load-on-start also run for real against a throwaway FalkorDBLite (empty DB -> loaded in 0.7 s with fake embeddings; second start skipped) |
| `scripts/falkordb_lite.py` (`make db-lite`) | ✅ | Used for all live verification on Oct 16 |
| README, RUNBOOK, DECISIONS, discovery brief | 🟡 | Drafts. Results, links and the AI disclosure are TODO |

## 4. Live verification results (Oct 16, FalkorDB 4.18.3 via FalkorDBLite, fake embeddings)

| Check | Result |
|---|---|
| `recent_changes(checkout, 24h)` | Red herring `deploy:990 → pr:479` (copy change) **and** `deploy:991 → pr:482` (2 hops) |
| `evidence_path(A-3001, 482)` via `algo.SPpaths` | `alert:A-3001 → svc:checkout → svc:promo-engine → svc:pricing ← deploy:991 → pr:482` (exactly the planned path) |
| `who_knows(pricing)` | page **Rahul** (owner/lead), consult **Marco** (score 98, now in Data) |
| `who_knows(ledger)` | Hana (page), Ines (consult), `bus_factor_1: true` |
| `trace_decision(svc:pricing)` as Arjun | ADR-011, the superseded wiki, INC-0307 and its postmortem; **1 restricted match, "ask the Pricing team"**, no thread content |
| Same as Dana | Also returns `thread:pricing-private-0142` |
| Same as Sam (contractor) | Nothing: PRs, deploys, ADRs and incidents are internal |
| Leak tests (`test_permissions_leak.py`, 16 cases) + regressions (`test_live_regressions.py`, 3) | All pass |
| e2e Story A (`test_e2e_story_a.py`) | Root cause `pr:482`, severity P1 (by code), exact evidence path, page Rahul and consult Marco, the invented citation dropped, the viewer never in model input; Dana can cite the private thread |
| Playbook loop | ✅ on Story A → Playbook saved (invented tool names filtered) → found for "dispatch assignment latency" |
| Query speed | Tool queries take 0.3–8 ms wall-clock on a laptop |

**Answers to the plan's "Day 1 checks" (plan section 9 / L.11):**
1. `algo.SPpaths` with `weightProp: 'w'` **works** even though only `DEPENDS_ON` edges carry `w`. The others count as 1; Story A's path weight is 5.0.
2. The vector `score` is a **distance: lower = closer.** Identical text scores about 0.
3. A path pattern inside `WHERE` (the permission check) **works**, with one FalkorDB 4.18 quirk (C-02): it fails with "Type mismatch: expected Null but was Pointer" when that `WHERE` is attached to a `WITH` that also computes a new value (e.g. `WITH viewer, n, coalesce(...) AS level WHERE ... OR (viewer)-[...]-(n)`). It also fails on nodes taken from `startNode(r)`/`endNode(r)`. Workarounds: add a pass-through `WITH viewer, n, level` before the `WHERE`, or collect the viewer's granted ids first and test with `IN`. The error only fires when the pattern is actually evaluated (i.e. for restricted nodes), so it hides in tests that only touch open data.
4. `vec.cosineDistance()` **exists and works.** `memory_find_playbooks` uses it for a scan without an index.

## 5. Challenges hit while building, and how they were resolved

| # | Challenge | Resolution |
|---|---|---|
| C-01 | Docker isn't installed, so there was no FalkorDB to test against | Found **FalkorDBLite** (an embedded FalkorDB). Added `make db-lite` (port 6390) and verified everything live |
| C-02 | FalkorDB pattern-predicate quirk (§4 item 3). It broke 4 queries for restricted nodes: `graph_neighbourhood`, `find_entity` (Dana could not find a thread she may see), `visible_ids` and `post_audience_check` (the planned on-camera block) | `graph_neighbourhood` uses a `granted` id list; the other three get a pass-through `WITH`. `tests/test_live_regressions.py` guards them. **Avoid that shape in new queries** |
| C-03 | The loader and `FakeLLM` used two different fake-embedding functions, so an offline-loaded graph would not match offline queries | One function (`lore.loader.embed.fake_embedding`), plus a new setting `LORE_FAKE_EMBEDDINGS`. The API, tools and loader all follow it |
| C-04 | The full-text search queried a `Chunk` full-text index that the loader never created | Added `createNodeIndex('Chunk', 'text')` to `loader/indexes.cypher` |
| C-05 | `create_app(settings)` ignored its settings for FalkorDB, because `db.get_graph()` always read the env | `db.get_graph(settings)` caches one client per host, port and graph; the app overrides `get_settings` |
| C-06 | `mcp>=1.2` resolved to mcp 2.3, where `FastMCP` was renamed `MCPServer` | `mcp_server.py` handles both; pinned `mcp>=2.3,<3`, `google-genai>=2.31,<3`, `falkordb>=1.8,<2` |
| C-07 | Import cycle: `llm` → `tools` → `retrieval` → `tools` | `tools.py` imports `retrieval`, `rerank` and `actions` lazily inside functions |
| C-08 | Tools are sync but embeddings are async | `tools.embed_query()` / `set_embedder()` hook; the fake path needs no event loop |
| C-09 | FalkorDB rejects a parameter as a variable-length path bound | `graph_neighbourhood` uses a `__HOPS__` token that Python replaces with a whole number from 1 to 3 |
| C-10 | `run_investigation` created its own `inv:` id, while the API had a run id | Resolved (FIX_LOG F-22): the API passes its run id to the supervisor, so the stream, the Investigation node and feedback share one id |
| C-12 | **Real leak found in review:** as Sam (contractor), `run_cypher` returned whole `Finding` nodes, whose text can come from other viewers' restricted investigations. `visible_ids` treated every node without `access_level` as visible, and the MCP server exposed `run_cypher` | `visible_ids` now only treats org/structure labels as open; memory nodes are never visible through it. The MCP server no longer exposes `run_cypher` or `propose_action`. A regression test was added. The root fix (access levels on Findings) is PENDING T-10 |
| C-11 | The Story bible's PR numbering and dates aren't monotonic (e.g. #479 merged after #482; deploy 990 after 991) | Kept as written; flagged for review (HUMAN_REVIEW R-02) |
| I-01 | The FalkorDB image's `run.sh` ignores command-line arguments (read from the image layer): it builds `redis-server ${REDIS_ARGS} --protected-mode no --dir $FALKORDB_DATA_PATH --loadmodule falkordb.so ${FALKORDB_ARGS}` itself. The plan's "pass `--requirepass` as the container command" would have started FalkorDB **without a password** and with no error | The container entrypoint is `sh -c 'export REDIS_ARGS="--requirepass $FALKORDB_PASSWORD --appendonly yes"; exec run.sh'` (ECS and `docker-compose.yml`). The data directory is confirmed: `run.sh` already uses `--dir /var/lib/falkordb/data` |
| I-02 | `GRAPH.RO_QUERY` on a graph that does not exist yet fails with "Invalid graph operation on empty key". On a brand-new ECS database that made the startup check (`RETURN 1`) fail, so load-on-start would never have run | `api/main.py` treats that error as "server reachable, graph missing" and loads the data. Verified on a real FalkorDBLite. Left for the lead: `/api/health` (`routes.py`) still reports `falkordb: false` until the graph exists |
| I-03 | The uv image tag `0.11` and the base image were unverified for arm64; Docker Hub pull limits can break CodeBuild | `ghcr.io/astral-sh/uv:0.11.3` (index lists linux/arm64, checked via the registry API); `python:3.12-slim` from AWS's public ECR mirror (arm64 checked); `uv` resolves wheels for aarch64 for all locked dependencies (`uv pip install --dry-run --python-platform aarch64-unknown-linux-gnu --only-binary :all:`) |

## 6. How the skeleton was built

Built on Oct 16 by Claude Code. The lead session wrote the contracts (`models.py`, `db.py`, `tools.py` registry, `permissions.py`, `report.py`, `PROJECT_CONTEXT.md`, `story-bible.md`). Six subagents then worked in parallel on separate files:
- **Sonnet 5.5** for the well-scoped packages: tools/queries/policy, data/loader/golden set, API/actions/replay/MCP/eval, frontend, and infra/README.
- **The base model (Opus)** for the LLM wrapper, agent loop, supervisor, memory and Ask.

The lead session then did the integration fixes (C-02 to C-05, C-12), the live verification and these docs. Disclose this in the README (HUMAN_REVIEW R-03).

## 7. How to reproduce the verification

```bash
make setup
make db-lite                                   # terminal 1 (or `make db` with Docker)
echo 'LORE_FALKORDB_PORT=6390' >> .env; echo 'LORE_FAKE_EMBEDDINGS=true' >> .env
make load-fake                                 # loads org_kettle
cd backend && set -a && . ../.env && set +a
uv run pytest -q                               # 296 passed (274 unit + 22 integration)
make mock                                      # UI on fake data, no backend needed
```
