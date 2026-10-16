# Lore: pending tasks

> **Last updated:** Oct 16 2026, after the skeleton build. Ordered by what unblocks the demo first.
> Priorities follow plan section 15: **P0** = must have, **P1** = should have, **P2** = nice to have. "Owner: Ayan" marks tasks only Ayan can do (accounts, keys, decisions). Everything else can be picked up by an agent: read `PROJECT_CONTEXT.md` and `STATE.md` first.
> Feature freeze: **Sun Oct 18, 12:00 IST.** Submit by about 19:00 IST (hard deadline 23:59 IST).

## Now (Oct 16–17): unblock the live demo

| # | P | Task | Owner | Notes |
|---|---|---|---|---|
| T-01 | P0 | **Get a Gemini API key with billing**, put it in `.env` as `LORE_GEMINI_API_KEY` | Ayan | Everything LLM-side is unverified until this exists |
| T-02 | P0 | Confirm the model ids (`LORE_MODEL_PRO`, `LORE_MODEL_FLASH`, `LORE_MODEL_EMBED`) in AI Studio | Ayan | `config.py` holds placeholders: `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gemini-embedding-001` |
| T-03 | P0 | Run `GeminiLLM` live once: one tool-calling turn plus one structured call, and fix any SDK mismatches | agent | Check `parameters_json_schema` with `anyOf`/defaults, function responses sent as role `user`, thought signatures kept in history, `resp.parsed` with a Pydantic schema (STATE §3, `llm.py`) |
| T-04 | P0 | Real embeddings: `make load` (not `load-fake`) with `LORE_FAKE_EMBEDDINGS=false`; re-run the integration tests | agent | 579 chunks ≈ 12 embedding calls. Check the vector index dimension (768) matches |
| T-05 | P0 | Run Story A live: `POST /api/investigations` as arjun, watch the SSE stream, and tune the 4 agent prompts until the root cause is `pr:482` in 5 of 5 runs | agent + Ayan | Prompts are in `lore/agents/*.py`. Ayan should rewrite them in his own words (HUMAN_REVIEW R-05) |
| T-06 | P0 | Run the frontend against the real API (`make api` + `make web`), and fix any contract mismatches | agent | It has only run in mock mode. See the frontend contract notes below (T-20 to T-24) |
| T-07 | P0 | Story B live: ✅ feedback on a Story A run → playbook → A-3002 solved in fewer steps; record the step counts | agent | The memory loop is verified with a scripted model (`test_e2e_story_a.py`) |
| T-08 | P0 | First full eval run: `make eval` (Graph ON vs OFF). Put the baseline in `DECISIONS.md` | agent | `eval/run.py` has never run end to end |
| T-09 | P0 | Ask the brain live: the 5 question types from plan section 10, as each persona | agent | `ask.py` is only unit-tested |
| T-10 | P0 | **Finding/Step nodes inherit no access level.** A Dana investigation's Finding can summarise a restricted thread. Today it is protected by per-viewer run ownership, by `visible_ids` refusing memory labels, and by the MCP server not exposing `run_cypher` (C-12: a real leak through `run_cypher` was found and closed on Oct 16). Fix: stamp each Finding with the strictest `access_level` of its citations, copy `VISIBLE_TO`, and filter on read. Add a leak test | agent | Security. Root-cause fix for C-12 |

## Day 3 (Oct 17): actions, failures, polish

| # | P | Task | Owner | Notes |
|---|---|---|---|---|
| T-11 | P0 | Slack workspace + incoming webhook → `LORE_SLACK_WEBHOOK_URL`; approve one post for real | Ayan | Without it, posts are marked "simulated" |
| T-12 | P1 | GitHub demo repo + fine-grained token (Issues: write) → `LORE_GITHUB_REPO`, `LORE_GITHUB_TOKEN` | Ayan | |
| T-13 | P0 | The on-camera failure: Responder quotes `#pricing-private` in an `#incidents` post → approve is blocked with a reason. Verify live with Dana | agent | `post_audience_check.cypher` is only unit-tested |
| T-14 | P1 | Other failure cases (plan section 11): tool timeout + backoff, bad model output + retry, policy blocks, Gemini down → replay. Fill the README failure table with what actually happened | agent | |
| T-15 | P0 | Record real replays: `story_a_<persona>.jsonl` for all 4 personas, plus `story_b_arjun.jsonl` (wrap `emit` with `replay.Recorder` where the demo run starts) | agent | Only a hand-written sample exists now |
| T-16 | P1 | MCP server in Gemini CLI: add it to `~/.gemini/settings.json` and run 3 tools | agent + Ayan | Snippet in the `mcp_server.py` docstring |
| T-17 | P1 | Replace the placeholder `PRICES` in `observability.py` with current Gemini prices | agent | Needed before quoting cost in the README/video |
| T-18 | P1 | Rerank weight tuning on the golden set; write the final weights in `DECISIONS.md` | agent | |
| T-19 | P1 | Optional `text_gen`: `make text` (Gemini writes realistic Slack/ticket text once), then `make gen`, tests, commit `data/text` + `data/*.json` | agent | Changes the data; re-run evals afterwards |

## Contract follow-ups (small, from the subagents' reports)

| # | P | Task |
|---|---|---|
| T-20 | P1 | Add optional `nodes: [{id, label, name}]` to the `tool_result` SSE payload, so the UI can label nodes outside the loaded 2-hop view (e.g. `pr:482`). The frontend already handles it if present |
| T-21 | P1 | Add `restricted_owner_hint` to the `tool_result` payload table in PROJECT_CONTEXT §6 (the UI types it as optional) |
| T-22 | P2 | `Action.note` field (today, "simulated…" and HTTP errors are stored in `blocked_reason`) |
| T-23 | P2 | `AskAnswer.message` for refusal text (today it's an uncited `claims[0]`) |
| T-24 | P2 | `run_investigation(..., investigation_id=None)` so the API's run id is the graph id (removes the remap in `api/runs.py`) |
| T-25 | P2 | Decide the restricted-hint wording once ("ask the Pricing team" vs "the Pricing team"); the UI copes with both |

## Day 4 (Oct 18): ship

| # | P | Task | Owner |
|---|---|---|---|
| T-30 | P0 | Install Docker Desktop (or use the VM directly), run `docker compose up`, and verify the `falkordb/falkordb` data path and healthcheck | Ayan |
| T-31 | P0 | VM + domain + Caddy: `make deploy VM_HOST=…`. Set `LORE_SESSION_SECRET`, a FalkorDB password, and `LORE_CORS_ORIGINS` = the Vercel URL | Ayan + agent |
| T-32 | P0 | Frontend on Vercel (`VITE_API_BASE`); check cross-site cookie + SSE (`SameSite=None; Secure`) from a phone | Ayan + agent |
| T-33 | P0 | Landing page with one "▶ Run the 3 AM incident" button; rate limit on (already in the API) | agent |
| T-34 | P0 | README: fill in the eval results table, failure table, live link, video and AI disclosure (R-03) | Ayan |
| T-35 | P0 | Video (plan section 16) and submission checklist (plan section 21) | Ayan |
| T-36 | P1 | Push to a public GitHub repo; make sure CI is green (the integration job is `continue-on-error` until it passes once) | Ayan |
| T-37 | P2 | Blog post, build-in-public posts | Ayan |

## P2 backlog (only if P0 + P1 are done)

3D intro shot · Org X-ray (CDLP communities) · second tenant `org_demo2` demo · load a real public GitHub repo · back-test Kettle's 10 past incidents · pause/resume in the UI · embedding-similarity entity resolution (the third method in plan section 19) · URL state in the frontend (a reload loses the run) · put the Actions panel above the report on 1080p (frontend note).
