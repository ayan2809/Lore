# Human review: things that need Ayan

> **Last updated:** Oct 18 2026 (deadline 23:59 IST tonight), after the first live local test round (see [FIX_LOG.md](FIX_LOG.md)) and the infra build.
>
> **How to answer:** write on the `> **Answer:**` line under the item (e.g. `> **Answer:** OK with C1–C8, but use ayan2809/kettle-incidents`), then tick the box `[x]` when nothing more is needed. A short answer is fine: "OK", "change X to Y", "skip". Agents read this file before working and act on your answers. They never tick a box or invent an answer for you.
>
> Agents: add new items at the bottom of the right section with the next free number (next free: **R-37**).

## Before deploying to AWS: what is still open

The infra is built and validated (cfn-lint, `validate-template`, shellcheck, 304 unit tests), and local live testing passed ([FIX_LOG.md](FIX_LOG.md)). **The agent stopped before deploying because these need you:**

1. ~~R-31 public-URL protection~~ **built** (daily cap). Still yours: raise the budget, Gemini spend alert, and pick the secrets command (C10).
2. ~~R-34~~ keep `gemini-3.8-flash` (decided).
3. ~~R-32~~ key rotated (done).
4. **R-36:** the Slack message format (proposal below).
5. Then run the deploy yourself (R-12 has the exact commands), or tell an agent "deploy".

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
  - [ ] Deploy (built Oct 18; commands from `infra/deploy.sh`, all as `ayan-mac`):
    1. `make aws-deploy`: creates `lore-network` + `lore-registry`, then **stops** because the secret `lore/app` still holds `CHANGE_ME`.
    2. `make aws-secrets-from-env` (C10: copies the Gemini key, Slack webhook and GitHub token from `.env`, never printing them) **or** `make aws-secrets` (hidden prompts). Both generate the session secret and FalkorDB password.
    3. `make aws-deploy` again: image build in CodeBuild (ARM64), the ECS app, the website. Prints `https://dxxxx.cloudfront.net` (30–45 min the first time; on first boot the API loads the graph with real embeddings, ~2–5 min).
    4. `make aws-status`, `make aws-logs` to check; `make aws-destroy` to tear everything down (type `lore`).
  - [ ] Local tools: `brew upgrade awscli`, `brew install --cask session-manager-plugin` (optional: `brew install shellcheck`)
  > **Answer:** - yes the github token is scoped only to the kettle incidents. 

- [x] **R-29 · First live run with Gemini, locally (no Docker needed).** *Done by an agent on Oct 18 with your test config; 14 fixes in [FIX_LOG.md](FIX_LOG.md). You can still click through it yourself with the steps below.* Steps:
  1. In `.env`, set `LORE_FALKORDB_PORT=6390` (done by Ayan, Oct 18), and fix the doubled `LORE_GITHUB_REPO` line (R-12). Keep `LORE_FAKE_EMBEDDINGS=false`. With the Slack webhook and GitHub token now set, approving an action locally **posts for real** to Slack and opens a real issue in `kettle-incidents`.
  2. Terminal 1: `make db-lite`.
  3. Terminal 2: `make load`, then `make api`.
  4. Terminal 3: `make web`, then open http://localhost:5173 and click "▶ Run the 3 AM incident" as Arjun.

  Write here what broke (or "worked"), so an agent can fix it.
  > **Answer:** (agent) Story A/B, Ask, SSE, real Slack post + GitHub issue #1, and the UI all work locally. See FIX_LOG.

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
  5. **Which secrets command (C10)?** Both are built: `make aws-secrets-from-env` (copies the Gemini key, Slack webhook and GitHub token from your local `.env`, never printing them) or `make aws-secrets` (hidden prompts). Pick one; nothing else depends on it.
  > **Answer:** (Ayan, Oct 18) Item 3: option (a), a global daily cap. **Built:** 100 live investigations per UTC day, then the recorded run, with a note in the trail; plus 1,000 Ask questions per day, then 429 (`LORE_LIVE_RUNS_PER_DAY`, `LORE_LIVE_ASKS_PER_DAY`, CloudFormation `LiveRunsPerDay`/`LiveAsksPerDay`). Item 4: keep 1 vCPU / 2 GB. **Still yours:** item 1 (raise the $12 AWS budget), item 2 (Gemini spend alert), item 5 (which secrets command).


- [x] **R-32 · Rotate the Gemini API key.** During testing, a malformed `.env` line made bash print part of the key into this session's tool output (FIX_LOG F-01). It never went into git or any file in the repo. Create a new key in AI Studio, put it in `.env`, delete the old one, and use the new one for the AWS secret.
  > **Answer:** Done by Ayan (Oct 18). An agent checked it works (embeddings + Flash-Lite) and that it differs from the old key (hash comparison); the local backup holding the old key was deleted. Delete the old key in AI Studio if you haven't.

- [x] **R-34 · Reasoning model: keep `gemini-3.8-flash` or switch to `gemini-4-argon`?** Measured on Oct 18 (FIX_LOG, last section): both 3/3 correct with the same red-herring rejection; 3.8-flash is ~1.5× faster ($0.022–0.024 vs $0.040–0.043 per investigation), and Argon doubles in price on Dec 1. **Recommendation: keep 3.8-flash** (the infra default `ModelPro=gemini-3.8-flash`). Also: keep `gemini-3.5-flash-lite` for the other agents and Ask?
  > **Answer:** Keep `gemini-3.8-flash` (Ayan, Oct 18): faster, cheaper, correct on the evals. Infra default `ModelPro=gemini-3.8-flash`.

- [ ] **R-35 · Things the live test showed you should know before the demo:**
  - **Real actions went out:** one Slack post to your webhook channel and GitHub issue #1 in `kettle-incidents`, both prefixed "[Lore local test - please ignore]". Delete or close them before recording if you like.
  - **New policy (F-09):** GitHub issues may not cite restricted or confidential sources, because the repo is public. A blocked draft can be fixed by dropping citations (`PATCH /api/actions/{id}` with `cited_ids`); the UI has no button for that yet (PENDING).
  - **Who to contact is now decided by code (F-03):** page = the owning team's lead of the service where the root cause landed; consult = top 2 experts; notify = the PR author. The model only words it.
  - **Story B memory demo:** with the learned playbook the Investigator takes **4 steps instead of 8** (not "11 → 4" as the plan's video script says). Use the measured numbers in the video.
  - **First run on AWS:** about a minute of downtime per deploy (single task); the FalkorDB image is pulled from Docker Hub anonymously (a rate-limit failure is fixed by `infra/deploy.sh restart`).
  > **Answer:**


- [ ] **R-36 · The Slack message is informative but badly presented** (Ayan, Oct 18). Today the model writes free text with raw graph ids (`pr:482`, `person:rahul`), with no structure, no links and no @mentions. Proposed fix (needs your OK):
  1. **Code builds the message, not the model.** A Slack Block Kit message made from the structured report:
     - a header with severity and alert;
     - root cause, why it matters, and what was ruled out;
     - the people;
     - links.
     Ids become human names ("PR #482 by Priya Nair", "ADR-011"). The model's text shrinks to one editable summary line, so nothing invented reaches Slack.
  2. **Links:** "Open Lore" (the public CloudFront URL) and the GitHub issue (if it was approved first). The PRs and ADRs are fictional, so they have no real URLs; they appear as names.
  3. **@mentions:** an optional map from person to Slack member id (`LORE_SLACK_USER_IDS`), e.g. map Rahul to your own Slack id so the page lights up in the demo. Without the map, names are shown in bold.
  4. The same citation and audience checks still run before anything is sent.
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
  - **Graph zoom at the end of a live run** (seen Oct 18): after the last step, the auto-zoom leaves the graph cramped in one corner with overlapping labels. Suggestion: zoom to the evidence path when the report arrives. OK to change?
  > **Answer:**

- [ ] **R-33 · Sam's report says "100 restricted sources matched".** For a contractor almost everything is internal, so the count hits the search limit. It's correct but reads oddly on screen. Show "many (100+)" instead, or leave it?
  > **Answer:**

- [ ] **R-17 · Offline gotcha.** Approving a replayed Slack action with FalkorDB down is blocked (fail-closed). Fine?
  > **Answer:**

- [x] **R-15 · Prices.** Looked up by an agent on Oct 18 (ai.google.dev pricing, paid tier, per 1M tokens): `gemini-4-argon` $2.00 in / $10.00 out (doubles Dec 1 2026); `gemini-3.8-flash` $0.75 in / $3.75 out (doubles Jan 1 2027); `gemini-embedding-2` $0.20 in. Thinking tokens are billed as output. Done: in `observability.PRICES`, plus `gemini-3.5-flash-lite` $0.30 in / $2.50 out (FIX_LOG F-05).
  > **Answer:** (none needed)

## D. Security and config (rewritten Oct 18 for AWS)

- [ ] **R-13 · Production settings in the AWS plan.** Confirm you're OK with all of these:
  - Session secret and FalkorDB password: **generated** by `deploy.sh secrets`, stored only in Secrets Manager `lore/app`.
  - `X-Origin-Verify` secret: generated by the `lore-registry` stack in Secrets Manager `lore/origin-verify` (not SSM: the deployer policy has no SSM write), never in git.
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
    - `gemini-embedding-2` accepts 768 dimensions (you confirmed); it needs one `Content` per text (FIX_LOG F-02);
    - the uv image `0.11.3` and the `python:3.12-slim` mirror exist for arm64; every Python dependency has an aarch64 wheel;
    - the FalkorDB image runs as root, has `redis-cli`, and its `run.sh` builds the command from `$REDIS_ARGS` (so the password goes there, not as command arguments; the plan's C3 was wrong and the infra agent corrected it);
    - `TIMEOUT_DEFAULT` / `TIMEOUT_MAX` exist in FalkorDB 4.18.
  - **Still unverified until the first deploy:**
    - Redis actually persists to EFS (restart test);
    - our image builds on arm64 (wheels, uv image tag);
    - SSE works through CloudFront for a whole investigation;
    - the cookie works on the CloudFront URL from a phone;
    - first CloudFront use on this account (some new accounts need verification).

  Nothing to answer unless you want to change the plan. Tick it after the first deploy checks pass.
  > **Answer:**

## E. Done / FYI

- [x] **R-04 · Gemini key + model ids.** Done by Ayan (Oct 18): `gemini-4-argon` (Pro), `gemini-3.8-flash` (Flash), `gemini-embedding-2` at 768 dims, all set in `.env`. Testing config since Oct 18 (`.env` and `config.py` defaults): `LORE_MODEL_PRO=gemini-3.8-flash`, `LORE_MODEL_FLASH=gemini-3.5-flash-lite` (see R-34).
- [x] **R-19 · Docker.** Resolved: not needed. Local dev uses `make db-lite` (real FalkorDB via FalkorDBLite), and AWS builds images with CodeBuild. Install Docker Desktop only if you want the FalkorDB Browser UI for a video shot.
- **R-20 · Schedule.** It's Oct 18 (deadline 23:59 IST). Order of work: R-29 local live run ∥ infra implementation → deploy → phone check → README/video. The plan's feature freeze is 12:00 IST today; after that, only fixes and finishing.
- **R-22 · Moved files.** The plan and the rules are in `docs/`; the FalkorDB HTML docs are in `docs/reference/` (gitignored).
- **R-23 · Git.** This repo is nested inside the `/Volumes/Projects` repo. The remote is `https://github.com/ayan2809/Lore.git` (`main`, `feature/initial-impl` pushed; `feature/aws-infra` local).
- **R-26 · Blog idea.** The FalkorDB 4.18 pattern-predicate quirk (STATE C-02) was found only by running the queries live.
