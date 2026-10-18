# Human review: things that need Ayan

> **Last updated:** Oct 18 2026 (deadline 23:59 IST tonight), after the AWS infra planning.
>
> **How to answer:** write on the `> **Answer:**` line under the item (e.g. `> **Answer:** OK with C1–C8, but use ayan2809/kettle-incidents`), then tick the box `[x]` when nothing more is needed. A short answer is fine: "OK", "change X to Y", "skip". Agents read this file before working and act on your answers. They never tick a box or invent an answer for you.
>
> Agents: add new items at the bottom of the right section with the next free number (next free: **R-32**).

## A. Do now (blocking deploy or demo)

- [x] **R-27 · Review the AWS infra plan** ([INFRA_PLAN.md](INFRA_PLAN.md)). Approve or change the 8 deviations from your brief (§2, C1–C8: ARM64, the `falkordb-server` image, password via the start command, the secret in the registry stack, the FalkorDB timeout override, the health-check grace period, `deploy.sh secrets`, the verified data path), and answer the 3 open questions (§11):
  1. OK with C1–C8?
  2. `LORE_GITHUB_REPO` = a separate demo repo, or `ayan2809/Lore`?
  3. After judging: tear down, or keep running?
  > **Answer:** - done 
  > *Recorded by agent from Ayan's Oct 18 message:* C1–C8 approved, including C2 (`falkordb-server`); the hackathon rules don't require the FalkorDB Browser. Q2: `ayan2809/kettle-incidents` (exists, public). Q3: moved to R-28. Log retention: asked for 2 days → CloudWatch doesn't allow 2, see R-30. `INFRA_PLAN.md` updated (C9, C10).

- [ ] **R-12 · AWS account and integrations** (rewritten Oct 18: AWS replaces the VM/Vercel plan)
  - [x] AWS account + CLI credentials: IAM user `ayan-mac`, region `ap-south-1`
  - [x] `LoreDeployer` managed policy attached (incl. `ReadQuotas`); access verified
  - [x] Quotas checked: Fargate 30 vCPU, 50 ALBs, 60 SG rules (enough)
  - [x] Budget alert ($12/month)
  - [x] Slack incoming webhook for the demo channel (in `.env`)
  - [x] GitHub demo repo `ayan2809/kettle-incidents` + fine-grained token (in `.env`)
  - [x] **Fix one line in `.env`:** it reads `LORE_GITHUB_REPO=LORE_GITHUB_REPO=ayan2809/kettle-incidents` (the key is doubled). Change it to `LORE_GITHUB_REPO=ayan2809/kettle-incidents`, otherwise GitHub issue creation will fail
  - [ ] Check the GitHub token is scoped to `kettle-incidents` only, with Issues: read & write
  - [ ] After the `lore-registry` stack exists: `make aws-secrets`. If you OK C10 (R-31 item 5), it copies the Gemini key, Slack webhook and GitHub token from your `.env` into Secrets Manager (prompting only for anything missing) and generates the session secret and FalkorDB password. Use the CLI as `ayan-mac`; no console or root needed
  - [ ] Approve and run the deploy command (an agent prepares it but never runs it)
  - [ ] Local tools: `brew upgrade awscli`, `brew install --cask session-manager-plugin` (optional: `brew install shellcheck`)
  > **Answer:** - yes the github token is scoped only to the kettle incidents. 

- [ ] **R-29 · First live run with Gemini, locally (no Docker needed).** The LLM side has never run live, so this is the biggest remaining risk. Steps:
  1. In `.env`, set `LORE_FALKORDB_PORT=6390` (done by Ayan, Oct 18), and fix the doubled `LORE_GITHUB_REPO` line (R-12). Keep `LORE_FAKE_EMBEDDINGS=false`. With the Slack webhook and GitHub token now set, approving an action locally **posts for real** to Slack and opens a real issue in `kettle-incidents`.
  2. Terminal 1: `make db-lite`.
  3. Terminal 2: `make load`, then `make api`.
  4. Terminal 3: `make web`, then open http://localhost:5173 and click "▶ Run the 3 AM incident" as Arjun.

  Write here what broke (or "worked"), so an agent can fix it.
  > **Answer:**

- [x] **R-28 · Budget vs runtime.** About $2.2/day while deployed, so $12 covers about 5 days. The rules file (`docs/hackathon-context.md`) gives no judging dates, so check Discord or the rules page for how long judges need the live link. Then: raise the budget, or tear down after judging (`make aws-destroy`) and rely on the video and replay?
  > **Answer:** Keep it running for at least 30 days (Ayan, Oct 18). **Follow-up needed:** at about $2.2/day the infra alone is about $66 for 30 days, plus Gemini usage, so the $12/month budget will trigger in about 5 days. See R-31.

- [x] **R-30 · Log retention: 1 or 3 days?** You asked for 2, but CloudWatch only accepts 1, 3, 5, 7, 14, 30… days. Retention hardly affects cost: storage is about $0.03 per GB-month and Lore writes well under 1 GB. What costs is ingestion (writing the logs), which is the same at any retention. **Recommendation: 3 days**, so logs survive through judging day for debugging. The plan uses 3 until you answer.
  > **Answer:** 3 days (Ayan, Oct 18).

- [ ] **R-31 · Running for 30 days: budget and abuse protection** (follow-up to R-28). Estimated 30-day cost ≈ **$90–110**: AWS ≈ $66 + Gemini ≈ $20–40 (see INFRA_PLAN §8.1). Decide:
  1. **AWS budget:** raise the $12/month alert to about $100 (as root: Billing → Budgets).
  2. **Gemini spend alert:** set a budget on the Google Cloud billing account behind your Gemini key (e.g. $40). AI Studio's spend is billed there, separately from AWS.
  3. **Public URL protection:** anyone with the link can start live investigations (about $0.20 each). Options:
     - (a) a global daily cap on live runs (e.g. 100/day), after which visitors get the recorded replay. *Recommended:* small code change, costs at most ~$20/day;
     - (b) live runs need a short demo code you give the judges; everyone else gets the replay;
     - (c) no extra protection: rely on the per-IP rate limit and the alerts.
  4. **Optional infra saving:** shrink the task from 1 vCPU / 2 GB to 0.5 vCPU / 1 GB (ARM). It saves about $0.55/day (~$16 per 30 days); the small graph fits, but investigations may feel slower. Keep 1 vCPU / 2 GB unless the budget is tight.
  5. **OK for INFRA_PLAN C10?** `make aws-secrets` copies the Gemini key, Slack webhook and GitHub token from your local `.env` into Secrets Manager (never printing them), and prompts only for missing values. The alternative is typing them in at hidden prompts.
  > **Answer:**

## B. Decisions an AI made that you must own (rules 12–13: "explain every part", "no AI slop")

- [ ] **R-03 · AI disclosure and ownership. Most important.**
  - **What AI wrote:** the plan was drafted by Claude in earlier sessions. The skeleton (about 7k lines of Python, 3k of TypeScript, 39 Cypher files) was written by Claude Code with six subagents on Oct 16, and the infra will be too. Rule 13 disqualifies projects "completely generated without meaningful human logic, architectural design, or technical understanding".
  - **Your own decisions so far:** the AWS architecture, the Fargate sizing, rejecting Lambda, and the CloudFront single-origin design. Say so in the README.
  - **What to do:**
    1. Read the code module by module: `models.py` → `permissions.py` → `queries/*.cypher` → `tools.py` → `agents/` → `api/` → `infra/cfn/`.
    2. Rewrite the README's AI-disclosure section in your own words.
  > **Answer:** - have written a section of this readme but will write once i have the full understanding. 

- [ ] **R-01 · Story bible** (`docs/story-bible.md`, drafted by Claude). Facts the data agent invented:
  - vendor limits (600 req/min; about 1,900 req/min at a 30s TTL; the next tier costing $4,200 a month more for 1,500 req/min);
  - the 33 generated people;
  - the titles of ADR-001 to 010 and 012 to 015;
  - 8 filler incidents;
  - Nikhil Rao as the author of PR #211, reviewed by Aisha;
  - `thread:general-0003` (the all-hands moving to Friday);
  - the text of the HR thread.

  Confirm or change these (then `make gen`, reload, run the tests).
  > **Answer:**

- [ ] **R-02 · Timeline oddities:**
  - PR #479 merges after #482;
  - deploy 990 (02:48) is numbered lower than deploy 991 (01:30);
  - PR #211 (March 2026) is numbered lower than late-2025 filler PRs.

  Keep or renumber?
  > **Answer:**

- [ ] **R-05 · Agent prompts and model choices.**
  - **Prompts to rewrite in your own words:** `lore/agents/*.py` and `COMMON_RULES` in `agents/base.py`.
  - **Models (your R-04 choices):** `gemini-4-argon` for the Investigator; `gemini-3.8-flash` for Triage, Historian, Responder, the report writer, playbooks and Ask.

  Should the final report writer use Pro instead of Flash?
  > **Answer:**

- [ ] **R-07 · Permission decisions.**
  - (a) PRs get the full viewer filter; deploys count as internal; services, people, teams, alerts and playbooks are visible to everyone.
  - (b) So Sam (contractor) sees no PRs, deploys, incidents or ADRs: his investigation is nearly empty.
  - (c) `who_knows` still returns the team lead to Sam.
  - (d) The restricted-match warning reveals that *something* exists.
  - (e) Restricted or confidential sources can never be cited in a non-private channel.

  Agree?
  > **Answer:**

- [ ] **R-06 · Source rank** (`DECISIONS.md` D-13): `ADR > runbook > postmortem > ticket > Slack > wiki`; PRs rank 0. The plan only specified `ADR > runbook > ticket > Slack`. Confirm?
  > **Answer:**

- [ ] **R-08 · `run_cypher` safety net.** No agent is given it, and it's hidden from MCP after the leak closed in STATE C-12. Recommendation: keep it disabled for the demo. OK?
  > **Answer:**

- [ ] **R-09 · Playbook privacy.** Playbooks only learn the symptom, the tool names and the root-cause *kind*, never tool outputs, so they're generic but can't leak. OK?
  > **Answer:**

- [ ] **R-10 · Tunables** (revisit after R-29 with real embeddings):
  - `RESTRICTED_MAX_DISTANCE = 0.5`
  - `PLAYBOOK_MAX_DISTANCE = 0.4`
  - recency half-life of 180 days
  - `MAX_ROWS_TO_MODEL = 20`
  - Ask `TOP_K = 8`

  Leave them to an agent's tuning on the golden set (PENDING T-18)?
  > **Answer:**

- [ ] **R-11 · Request policy is keyword rules** (`policy.check_request`); e.g. "roll back prod" is blocked unless it ends with "?". Read and adjust, or accept?
  > **Answer:**

- [ ] **R-16 · Story B has no "consult" person**, because Tomás is both the author and the top expert. Add a second eta-predictor expert to the story?
  > **Answer:**

- [ ] **R-24 · Golden questions** (`backend/eval/golden.jsonl`: 59 questions; `investigations.jsonl`: 3 scenarios), drafted by an agent. These are your eval design: read them and fix or add.
  > **Answer:**

## C. Product and UX (run `make mock`, add `?speed=3` to the URL)

- [ ] **R-14 · Frontend review.**
  - **Colours:** triage sky, historian violet, investigator emerald, responder pink.
  - **Wording:** "▶ Run the 3 AM incident", "▶ Run again as Dana", "Ruled out", "Dropped by the citation check".
  - **Actions panel:** on 1080p it's below the report. Move it above?
  - **Persona switch:** switching resets the run. Auto re-run instead?
  - **Mock timeout:** delete the deliberate timeout step in `mock.ts` for a cleaner video?
  > **Answer:**

- [ ] **R-17 · Offline gotcha.** Approving a replayed Slack action with FalkorDB down is blocked (fail-closed). Fine?
  > **Answer:**

- [x] **R-15 · Prices.** Looked up by an agent on Oct 18 (ai.google.dev pricing, paid tier, per 1M tokens): `gemini-4-argon` $2.00 in / $10.00 out (doubles Dec 1 2026); `gemini-3.8-flash` $0.75 in / $3.75 out (doubles Jan 1 2027); `gemini-embedding-2` $0.20 in. Thinking tokens are billed as output. Still to do (agent, PENDING T-17): put these into `observability.PRICES`.
  > **Answer:** (none needed)

## D. Security and config (rewritten Oct 18 for AWS)

- [ ] **R-13 · Production settings in the AWS plan.** Confirm you're OK with all of these:
  - Session secret and FalkorDB password: **generated** by `deploy.sh secrets`, stored only in Secrets Manager `lore/app`.
  - `X-Origin-Verify` secret: generated by `deploy.sh`, stored in SSM `/lore/origin-verify`, never in git.
  - The ALB accepts only CloudFront's IP list, and returns 403 without the header.
  - Cookie `HttpOnly; Secure; SameSite=Lax` (`LORE_COOKIE_SECURE=true` in ECS).
  - CORS empty (same origin).
  - Rate limit 20/min per viewer IP via `CloudFront-Viewer-Address`.
  - FalkorDB never exposed: localhost only, password-protected, encrypted EFS.
  - Your local `.env` keeps its own separate session secret.
  > **Answer:**

- [ ] **R-25 · Verification status of the infra assumptions.**
  - **Verified Oct 18:**
    - FalkorDB's data path is `/var/lib/falkordb/data` (from the image config);
    - `falkordb-server:v4.18.3` exists for arm64;
    - CodeBuild has ARM images in ap-south-1;
    - the API pings SSE every 15 s and runs a single uvicorn worker;
    - the quotas are enough;
    - `gemini-embedding-2` accepts 768 dimensions (you confirmed).
  - **Still unverified until the first deploy:**
    - Redis actually persists to EFS (restart test);
    - our image builds on arm64 (wheels, uv image tag);
    - SSE works through CloudFront for a whole investigation;
    - the cookie works on the CloudFront URL from a phone;
    - FalkorDB 4.18.3 accepts `TIMEOUT_DEFAULT` / `TIMEOUT_MAX`;
    - first CloudFront use on this account (some new accounts need verification).

  Nothing to answer unless you want to change the plan. Tick it after the first deploy checks pass.
  > **Answer:**

## E. Done / FYI

- [x] **R-04 · Gemini key + model ids.** Done by Ayan (Oct 18): `gemini-4-argon` (Pro), `gemini-3.8-flash` (Flash), `gemini-embedding-2` at 768 dims, all set in `.env`. Note: the defaults in `backend/lore/config.py` are still the old placeholders; the infra change will update them to these ids.
- [x] **R-19 · Docker.** Resolved: not needed. Local dev uses `make db-lite` (real FalkorDB via FalkorDBLite), and AWS builds images with CodeBuild. Install Docker Desktop only if you want the FalkorDB Browser UI for a video shot.
- **R-20 · Schedule.** It's Oct 18 (deadline 23:59 IST). Order of work: R-29 local live run ∥ infra implementation → deploy → phone check → README/video. The plan's feature freeze is 12:00 IST today; after that, only fixes and finishing.
- **R-22 · Moved files.** The plan and the rules are in `docs/`; the FalkorDB HTML docs are in `docs/reference/` (gitignored).
- **R-23 · Git.** This repo is nested inside the `/Volumes/Projects` repo. The remote is `https://github.com/ayan2809/Lore.git` (`main`, `feature/initial-impl` pushed; `feature/aws-infra` local).
- **R-26 · Blog idea.** The FalkorDB 4.18 pattern-predicate quirk (STATE C-02) was found only by running the queries live.
