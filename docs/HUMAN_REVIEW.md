# Human review: things that need Ayan

> **Last updated:** Oct 16 2026, after the skeleton build. Agents: add new items at the bottom of the right section with the next free number; never silently resolve an item that says "Ayan decides".
> Each item says **what**, **why it needs you**, and **what to do**. Tick the box when done.

## A. Blocking: needed before the live demo works

- [ ] **R-04 · Gemini key + model ids.** Create a key with billing (plan section 13 warns that free-tier limits will hurt a live demo). Put it in `.env` as `LORE_GEMINI_API_KEY`. Confirm the exact model ids in AI Studio. `config.py` holds placeholders: `gemini-3-pro-preview` (Investigator), `gemini-3-flash-preview` (everything else), `gemini-embedding-001` at 768 dimensions. **Nothing on the LLM side has run live yet** (STATE §3).
- [ ] **R-12 · Accounts and destinations:**
  - a Slack workspace + incoming webhook → `LORE_SLACK_WEBHOOK_URL`;
  - a throwaway GitHub repo + fine-grained token with Issues: write → `LORE_GITHUB_REPO`, `LORE_GITHUB_TOKEN`;
  - a VM (provider, SSH user) → `VM_HOST` for `make deploy`;
  - a domain + DNS A record → `LORE_DOMAIN`;
  - a Vercel project → its URL goes in `LORE_CORS_ORIGINS`;
  - the public GitHub repo name for the submission.

  Without the webhook and token, actions are marked "simulated", so the demo still runs.
- [ ] **R-19 · Docker.** It isn't installed on this Mac. For local work, `make db-lite` runs the **real FalkorDB module** via FalkorDBLite (that's how everything was verified on Oct 16), but it has no FalkorDB Browser UI (port 3000). Install Docker Desktop if you want the Browser for the video's "under the hood" shot. The VM needs Docker either way.

## B. Review: decisions an AI made that you must own (rules 12–13: "explain every part", "no AI slop")

- [ ] **R-03 · AI disclosure and ownership. Most important.**
  - **What AI wrote:** the plan was drafted by Claude in earlier sessions. On Oct 16 the whole skeleton (about 7k lines of Python, 3k of TypeScript, 39 Cypher files) was written by Claude Code, using six subagents.
  - **Rule 13** disqualifies projects "completely generated without meaningful human logic, architectural design, or technical understanding".
  - **What to do:**
    1. Read the code module by module in this order: `models.py` → `permissions.py` → `queries/*.cypher` → `tools.py` → `agents/` → `api/`. Write down anything you can't explain.
    2. Change things to your taste, especially the prompts (R-05) and the permission rules (R-07).
    3. Rewrite the README's AI-disclosure section in your own words. The draft is honest about what Claude did, but you must state exactly what *you* decided.
- [ ] **R-01 · Story bible** (`docs/story-bible.md`). Drafted by Claude from the plan.
  - **Facts the data agent invented:**
    - Vendor limits: 600 req/min, about 1,900 req/min at a 30s TTL, and the next tier costing $4,200 a month more for 1,500 req/min.
    - The 33 generated people and their join dates.
    - The titles of ADR-001 to ADR-010 and ADR-012 to ADR-015.
    - Eight filler incidents.
    - Nikhil Rao as the author of PR #211, reviewed by Aisha.
    - The public `thread:general-0003` about the all-hands moving to Friday, so Sam has something answerable.
    - The text of the HR thread.
  - **What to do:** confirm these or change them, then run `make gen`, `make load-fake` and the tests.
- [ ] **R-02 · Timeline oddities in the story** (kept as written; your call):
  - PR #479 (the red herring) merges after PR #482.
  - Deploy 990 (02:48) is numbered lower than deploy 991 (01:30).
  - PR #211 (March 2026) is numbered lower than filler PRs from late 2025.

  Judges may not notice, but a careful one might. Renumber in `data_gen/story.py` if you care.
- [ ] **R-05 · Agent prompts and model choices.**
  - **Prompts to rewrite in your own words:** `lore/agents/triage.py`, `historian.py`, `investigator.py`, `responder.py`, and `COMMON_RULES` in `agents/base.py`. The Investigator's red-herring rules matter most.
  - **Model decision:** should the final report writer use Pro instead of Flash? Today only the Investigator uses Pro.
- [ ] **R-07 · Permission decisions made while building.** Check that you agree:
  - (a) PRs get the full viewer filter. Deploys count as `internal`. Services, people, teams, alerts and playbooks are visible to everyone.
  - (b) So **Sam (contractor) sees no PRs, deploys, incidents or ADRs**: his evidence path is empty. That's correct per "public only", but a Sam investigation will be nearly empty.
  - (c) `who_knows` still returns the owning team's lead to Sam, so there's always someone to page.
  - (d) The restricted-match warning reveals that *something* exists (the plan's documented trade-off).
  - (e) The post-audience check never allows a restricted or confidential source in a non-private channel, even if every current member could see it, because every employee can read an open channel.
- [ ] **R-06 · Source rank** (`DECISIONS.md` D-13). The plan has `ADR > runbook > ticket > Slack`. The build added `postmortem` (after runbook) and `wiki` (last); PRs rank 0. Confirm.
- [ ] **R-08 · `run_cypher` safety net.** It's implemented (read-only, forced LIMIT, permission post-filter), but **no agent is given it**, and it's now hidden from MCP after a real leak was found and closed (STATE C-12). Recommendation: leave it disabled for the demo, and mention it as a guarded escape hatch only if asked.
- [ ] **R-09 · Playbook privacy trade-off.** The playbook summariser only sees the symptom, the tool names and the *kind* of root cause (e.g. "pr"), never tool outputs, so shared memory can't carry restricted content. Playbooks are therefore generic. OK?
- [ ] **R-10 · Tunables to revisit once real embeddings exist:**
  - `RESTRICTED_MAX_DISTANCE = 0.5` (`retrieval.py`)
  - `PLAYBOOK_MAX_DISTANCE = 0.4` (`tools.py`)
  - rerank recency half-life of 180 days
  - `MAX_ROWS_TO_MODEL = 20`
  - Ask `TOP_K = 8`

  Tune these on the golden set (PENDING T-18).
- [ ] **R-11 · Request policy is keyword rules** (`policy.check_request`). For example, "roll back prod" is blocked unless it ends with "?". Simple and explainable, but expect false positives. Read the rules and adjust.
- [ ] **R-16 · Story B "consult" is empty**, because Tomás is both the PR author and the top eta-predictor expert. Add a second eta-predictor expert to the story if you want the "page vs consult" beat in Story B too.
- [ ] **R-24 · Golden questions** (`backend/eval/golden.jsonl`, 59 questions; `investigations.jsonl`, 3 scenarios). These were drafted by an agent. They are your eval design, so read them, fix wording, and add the cases you'd ask as a judge.

## C. Product and UX choices to look at (run `make mock` and click through)

- [ ] **R-14 · Frontend review in mock mode** (`make mock`, then add `?speed=3` to the URL to play faster).
  - **Colours:** triage sky, historian violet, investigator emerald, responder pink.
  - **Wording:** "▶ Run the 3 AM incident", "▶ Run again as Dana", "Ruled out", "Evidence (every claim cites a source)", "Dropped by the citation check", "CONFLICT: outranked by a newer or higher-ranked source".
  - **Layout:** on 1080p the Actions panel sits below the report and needs a scroll. Move it above, or auto-scroll?
  - **Persona switch:** switching persona resets the run, so the "switch to Dana" beat is a re-run. Want an auto re-run in replay mode instead?
  - **Mock timeout:** the mock includes a deliberate `recent_changes` timeout so the red error state shows. Delete those two steps in `mock.ts` for a cleaner video.
- [ ] **R-17 · Offline demo gotcha.** Approving a replayed Slack action while FalkorDB is down is **blocked** ("policy check could not run"). This is fail-closed by design. Fine for the live demo (FalkorDB will be up); just know it.
- [ ] **R-15 · Prices.** `observability.PRICES` holds placeholder numbers. Don't quote cost anywhere until they're replaced (PENDING T-17).

## D. Security and config before going public

- [ ] **R-13 · Production settings:**
  - set `LORE_SESSION_SECRET` (the API logs a warning while it's the default);
  - set a FalkorDB password (a commented `REDIS_ARGS` block in `docker-compose.yml`);
  - keep FalkorDB and Browser ports bound to 127.0.0.1 on the VM (already the case);
  - the rate limit is 20/min/IP. Behind Caddy, the client IP comes from `X-Forwarded-For`, so never expose the API directly.
- [ ] **R-25 · Unverified infra guesses** (check the first time you run Docker):
  - the `falkordb/falkordb` data path (`/var/lib/falkordb/data`);
  - the healthcheck uses `redis-cli`;
  - the `ghcr.io/astral-sh/uv:0.11` image tag exists;
  - cross-site cookie + SSE between Vercel and the VM work (`SameSite=None; Secure`).

## E. FYI (no action unless you disagree)

- **R-20 · Schedule.** The skeleton covers most of plan Day 1 and part of Day 2. Plan items not done: deploy an empty skeleton to the VM on Day 1, and the first eval run. See `PENDING_TASKS.md` for the re-planned order.
- **R-22 · Moved files.**
  - `plan.md` and `hackathon-context.md` are now in `docs/`.
  - The FalkorDB HTML docs and `build_docs.py` are in `docs/reference/`. The HTML is gitignored (7 MB, third-party), and `build_docs.py`'s output path was updated to match.
- **R-23 · Nested git repo.** `/Volumes/Projects` is itself a git repo. `Graph Hacks/` is now its own repo inside it (branch `feature/initial-impl`, base `main`), so the parent repo will show it as an untracked folder. Push this repo to its own GitHub remote; don't add it to the parent.
- **R-26 · FalkorDB quirk worth a blog paragraph** (STATE C-02): a permission path pattern after a computing `WITH` errors in FalkorDB 4.18. It was found because the queries were run live, not just unit-tested, which is a good "what I learned" story for build-in-public.
