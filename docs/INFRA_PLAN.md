# Lore on AWS: infrastructure plan

> **Status:** agreed with Ayan on Oct 18 2026. Changes C1–C9 approved (C10, reading secrets from `.env`, awaits Ayan's OK in R-31); GitHub repo `ayan2809/kettle-incidents`; logs kept 3 days; the deployment stays up for at least 30 days. Nothing has been implemented or deployed yet. **Still open:** R-31 in `HUMAN_REVIEW.md` (budget raise, Gemini spend alert, public-URL protection, optional smaller task, OK for C10). Implementation starts when Ayan says go.
> Based on Ayan's infra brief plus checks run against the real account and images on Oct 18. Where this plan differs from the brief, it says so in **§2 Changes vs the brief**.
> Branch: `feature/aws-infra` (created from `feature/initial-impl`).

## 1. The picture

```
                       Browser (phone / laptop)
                                │  HTTPS
                                ▼
          CloudFront  https://dxxxx.cloudfront.net   (one distribution)
             │  /*  (cached)                     │  /api/*  (no cache, all methods)
             ▼                                   ▼  HTTP + header X-Origin-Verify: <secret>
   S3 bucket (private, OAC)            Application Load Balancer (public, port 80)
   React build: index.html + assets       │  inbound only from CloudFront's IP list
                                          │  forwards ONLY if X-Origin-Verify matches, else 403
                                          ▼  port 8000
                            ┌──────── ECS Fargate task (ARM64, 1 vCPU / 2 GB) ────────┐
                            │  api container (our image, uvicorn, 1 worker)           │
                            │      │ localhost:6379 (password)                        │
                            │  falkordb container (falkordb/falkordb-server:v4.18.3)  │
                            │      │ /var/lib/falkordb/data                           │
                            └──────┼──────────────────────────────────────────────────┘
                                   ▼ NFS 2049 (encrypted)
                             EFS file system (graph survives restarts)

   Outbound from the task (public IP, no NAT): Gemini, Slack webhook, GitHub API.
   Secrets Manager secret "lore/app" → injected into the containers at start.
   ECR repo ← CodeBuild (ARM) builds the API image from a zip of backend/ (no Docker on the Mac).
```

**Why this shape:**
- **Fargate, not Lambda (D-14).** FalkorDB is a long-running server. Investigations stream over SSE for minutes, while API Gateway cuts off at about 30 s and Lambda freezes after it responds. The run registry also lives in process memory.
- **One task with a FalkorDB sidecar on EFS (D-15).** This is the cheapest setup that keeps the graph and the agents' memory across restarts.
- **The default CloudFront URL (D-16).** No certificate, no Route 53, no domain. The CloudFront → ALB hop is plain HTTP, guarded by CloudFront's IP list plus the secret header.

## 2. Changes vs the brief (C1–C9 approved by Ayan, Oct 18; C10 awaiting OK)

| # | Brief said | Plan does | Why (checked Oct 18) |
|---|---|---|---|
| C1 | x86_64 unless ARM64 is confirmed | **ARM64** for Fargate and CodeBuild | `falkordb-server:v4.18.3` is published for arm64; CodeBuild has native ARM images in ap-south-1 (`aws/codebuild/amazonlinux-aarch64-standard:3.0`). You approved ARM64. |
| C2 | Image `falkordb/falkordb:4.18.x` | **`falkordb/falkordb-server:v4.18.3`** | FalkorDB's docs recommend `-server` for production: same engine, no Browser UI, less memory. The hackathon rules only require FalkorDB to be the primary database doing real work (rules 2–3); the Browser is just a debugging tool there, and Lore's own React UI shows the graph. If you want a Browser shot for the video, run it locally (Docker), not on AWS |
| C3 | Password via `REDIS_ARGS=--requirepass …` from the secret | Inject the secret as env `FALKORDB_PASSWORD`, and set the container command to `run.sh redis-server --loadmodule … --requirepass "$FALKORDB_PASSWORD" --dir /var/lib/falkordb/data --appendonly yes` | ECS can't put a secret into the middle of a longer env value. The explicit `--dir` is also needed: the image sets `FALKORDB_DATA_PATH=/var/lib/falkordb/data`, but whether Redis actually writes there is unverified, and if it doesn't, EFS would stay empty |
| C4 | Secret created in `app.yaml` | **Secret created in `registry.yaml`** (the second stack) | The secret must hold the real Gemini key **before** the first task starts: `LORE_LOAD_ON_START` embeds the data with Gemini on first boot. So the flow is registry stack → you fill the secret → app stack |
| C5 | (not mentioned) | Override the image's `FALKORDB_ARGS` to `MAX_QUEUED_QUERIES 25 TIMEOUT_DEFAULT 2000 TIMEOUT_MAX 30000 RESULTSET_SIZE 10000`, and the loader passes a 30 s timeout on its writes | The image ships with `TIMEOUT 1000` (a 1 s query cap). The loader's batched writes with embeddings could exceed that on a quarter vCPU |
| C6 | (not mentioned) | ECS service `HealthCheckGracePeriodSeconds: 180` | FalkorDB has to start, and on first boot the loader runs. The ALB must not kill the task while that happens (`/api/health` itself never waits for the loader) |
| C7 | `deploy.sh` documents `put-secret-value` | Add a `deploy.sh secrets` command: it **generates** `LORE_SESSION_SECRET` and `LORE_FALKORDB_PASSWORD` itself and asks for the other three values with hidden input | Fewer manual steps, and nothing lands in your shell history |
| C8 | Data path unverified (R-25) | `/var/lib/falkordb/data` | Read from the image config (`FALKORDB_DATA_PATH`) |
| C9 | Log retention 7 days | **3 days** (Ayan chose 3, R-30) | Ayan asked for 2 days to save money, but CloudWatch only accepts 1, 3, 5, 7, 14, 30… days, so 2 isn't valid. Retention barely changes the bill: storage costs about $0.03 per GB-month, and Lore writes well under 1 GB, so the difference is fractions of a cent. The real log cost is ingestion (about $0.50–0.70 per GB written), which is the same whatever the retention. 3 days keeps logs through judging day; 1 day risks losing them before you can debug |
| C10 | `deploy.sh secrets` prompts for values | It **reads the Slack webhook, GitHub token and Gemini key from your root `.env`** if they're set there, and prompts only for missing ones | You already keep them in `.env`, so no retyping. Values go straight to Secrets Manager and are never printed |

## 3. Stacks and resources

Four CloudFormation stacks, deployed in this order. All names start with `lore-`, which the `LoreDeployer` policy requires.

### 3.1 `lore-network` (`infra/cfn/network.yaml`)

| Resource | Why it exists |
|---|---|
| VPC `10.20.0.0/16` | Our own private network, separate from the default VPC |
| 2 public subnets (ap-south-1a, 1b) | An ALB needs at least 2 availability zones |
| Internet Gateway + route table | Lets the ALB receive traffic and the task call Gemini, Slack and GitHub. **No NAT gateway** (saves about $1/day) |
| SG `lore-alb-sg` | Inbound port 80 **only** from the prefix list `pl-9aa247f3` (CloudFront's origin-facing IPs in ap-south-1), in exactly one rule (it uses about 55 of the 60-rule quota) |
| SG `lore-task-sg` | Inbound 8000 only from `lore-alb-sg`. FalkorDB's 6379 is never opened (the containers share localhost) |
| SG `lore-efs-sg` | Inbound NFS 2049 only from `lore-task-sg` |
| Outputs | VPC id, subnet ids and SG ids, exported for the app stack |

### 3.2 `lore-registry` (`infra/cfn/registry.yaml`)

| Resource | Why it exists |
|---|---|
| ECR repo `lore-api` | Stores our API image. Scan on push; a lifecycle rule keeps the last 5 images |
| S3 bucket `lore-artifacts-<account>` | `deploy.sh` uploads `backend.zip` here for CodeBuild. Private, with objects expiring after 7 days |
| CodeBuild project `lore-api-build` + role `lore-codebuild-role` | Builds the ARM64 image in AWS (`ARM_CONTAINER`, privileged mode for Docker) and pushes `:<git-sha>` and `:latest`. The role can only read the artifacts bucket, push to `lore-api` and write its own logs |
| Secrets Manager secret `lore/app` | One JSON secret with placeholder values for all 5 keys (§5). CloudFormation sets the placeholder **only when it creates the secret**, so later stack updates never overwrite your real values |

### 3.3 `lore-app` (`infra/cfn/app.yaml`)

Parameters: `ImageTag`, `EmbedDim` (768), `CloudFrontPrefixListId`, `OriginVerifySecret` (NoEcho), `GithubRepo`, `ModelPro`, `ModelFlash`, `ModelEmbed`, `RateLimitPerMinute`.

| Resource | Why it exists |
|---|---|
| ECS cluster `lore` | The home for the service |
| Task definition (ARM64, 1024 CPU / 2048 MB) | Two containers: **`falkordb`** (256 CPU / 768 MB reserved; healthcheck `redis-cli -a $FALKORDB_PASSWORD ping`; EFS mounted at `/var/lib/falkordb/data`) and **`api`** (768 CPU / 1280 MB; port 8000; `DependsOn falkordb HEALTHY`; `LORE_FALKORDB_HOST=localhost`) |
| ECS service | `DesiredCount 1`, `MinimumHealthyPercent 0` / `MaximumPercent 100` (never two tasks: the run registry is in memory, and two FalkorDBs must never share one EFS directory), public IP on, `EnableExecuteCommand` on, grace period 180 s |
| ALB `lore-alb` + listener :80 | Default action: fixed 403. One rule forwards to the target group **only if** `X-Origin-Verify` equals the secret. Idle timeout 300 s (for SSE) |
| Target group | HTTP 8000, target type `ip`, health check `/api/health` → 200, deregistration delay 10 s |
| EFS file system + 2 mount targets + access point | Encrypted at rest. The access point pins the uid/gid and the root directory `/falkordb`. Only the task SG can reach it |
| Log groups `/lore/api`, `/lore/falkordb` | 3-day retention (C9) |
| Execution role `lore-task-exec-role` | Pull from ECR, write logs, read **only** the `lore/app` secret |
| Task role `lore-task-role` | ECS Exec (`ssmmessages:*`) and EFS client mount/write on the access point. Nothing else: the app calls no AWS APIs |

Non-secret environment for `api`:
- `LORE_GRAPH_NAME=org_kettle`, `LORE_MODEL_PRO=gemini-4-argon`, `LORE_MODEL_FLASH=gemini-3.8-flash`, `LORE_MODEL_EMBED=gemini-embedding-2`, `LORE_EMBED_DIM=768`;
- `LORE_GITHUB_REPO=ayan2809/kettle-incidents`, `LORE_FAKE_EMBEDDINGS=false`, `LORE_RATE_LIMIT_PER_MINUTE=20`, `LORE_CORS_ORIGINS=[]`;
- `LORE_COOKIE_SECURE=true`, `LORE_LOAD_ON_START=if_empty`, `LORE_QUERY_TIMEOUT_MS=2000`.

### 3.4 `lore-frontend` (`infra/cfn/frontend.yaml`)

| Resource | Why it exists |
|---|---|
| S3 bucket `lore-web-<account>` | The React build. Block all public access |
| Origin Access Control + bucket policy | Only this CloudFront distribution may read the bucket |
| Origin request policy `lore-api-forward` | Forwards all cookies, query strings and viewer headers except `Host`, **plus** `CloudFront-Viewer-Address` and `CloudFront-Forwarded-Proto` |
| CloudFront distribution (`PriceClass_200`, which includes India) | Origin A = S3 (OAC). Origin B = the ALB (http-only, header `X-Origin-Verify`, read timeout 60 s, keep-alive 60 s). Behaviour `/api/*`: all methods, `CachingDisabled`, our request policy, no compression. Default: S3, `CachingOptimized`, redirect to HTTPS, `index.html` as the root. **No** custom error responses (they would turn the API's deliberate 404s into HTML) |
| Outputs | `PublicUrl`, `DistributionId`, `BucketName` |

## 4. `infra/deploy.sh`

`set -euo pipefail`, region `ap-south-1` by default (`AWS_REGION` overrides it). Every step is safe to re-run.

| Command | Does |
|---|---|
| `deploy` | Everything below, in order |
| `secrets` | Generate the session secret and FalkorDB password; take the Gemini key, Slack webhook and GitHub token from the root `.env` (prompting with hidden input only for missing ones, C10); `put-secret-value` into `lore/app` |
| `backend-only` | Zip `backend/` (without `.venv`, caches or tests) → S3 → start CodeBuild → wait → deploy `lore-app` with `ImageTag=<git sha>` → wait until the service is stable |
| `frontend-only` | `npm ci && VITE_API_BASE= npm run build` → deploy `lore-frontend` → `s3 sync` (hashed assets cached for a year, `index.html` no-cache) → invalidate `/index.html` |
| `status` | Stack states, running task, health of the ALB target, public URL |
| `logs [api\|falkordb]` | `aws logs tail --follow` |
| `exec` | ECS Exec shell into the `api` container (needs the Session Manager plugin) |
| `rollback <tag>` | Redeploy `lore-app` with an older `ImageTag` |
| `destroy` | Asks you to type `lore`, empties the buckets and ECR, then deletes the stacks in reverse order |

The full `deploy` flow is:
1. validate the templates;
2. deploy `lore-network`;
3. deploy `lore-registry`;
4. **stop if the secret still holds placeholders**, and tell you to run `deploy.sh secrets`;
5. look up the CloudFront prefix list id and generate (or reuse) `OriginVerifySecret`, kept in SSM Parameter Store `/lore/origin-verify`, not in git;
6. build the image;
7. deploy `lore-app`;
8. deploy the frontend;
9. print the URL.

Makefile targets: `aws-deploy`, `aws-secrets`, `aws-frontend`, `aws-status`, `aws-logs`, `aws-destroy`.

## 5. Secrets (all in the one secret `lore/app`)

| Key | Who provides it | Notes |
|---|---|---|
| `LORE_GEMINI_API_KEY` | You (done) | |
| `LORE_SLACK_WEBHOOK_URL` | You (done: in `.env`) | A webhook for the channel the demo posts to |
| `LORE_GITHUB_TOKEN` | You (done: in `.env`) | Fine-grained token for `ayan2809/kettle-incidents` only, **Issues: read & write**, short expiry |
| `LORE_SESSION_SECRET` | `deploy.sh secrets` generates it | Signs the session cookie |
| `LORE_FALKORDB_PASSWORD` | `deploy.sh secrets` generates it | Used by both containers |

Not in this secret: `OriginVerifySecret`. `deploy.sh` generates it and keeps it in SSM Parameter Store, since CloudFront and the ALB both need it at deploy time.

**How you'll store them: CLI as `ayan-mac`, no console needed.** Run `make aws-secrets` after the registry stack exists. Your `LoreDeployer` policy already allows Secrets Manager on `lore/*`.
- If you prefer the console, sign in **as `ayan-mac`**, not root. This needs console access enabled for that user. Go to Secrets Manager → `lore/app` → Retrieve secret value → Edit.
- **Don't create the secret by hand before the stack runs:** the names would collide and the stack would fail.

## 6. Code and docs changes in the same branch

| Where | Change |
|---|---|
| `lore/config.py` | Add `cookie_secure: bool = False`, `load_on_start: Literal["never","if_empty"] = "never"`, `falkordb_password` already exists |
| `lore/api/session.py` | Cookie flags: `HttpOnly`, `SameSite=Lax`, `Secure = settings.cookie_secure` (no more guessing from CORS origins) |
| `lore/api/ratelimit.py` | Client IP = `CloudFront-Viewer-Address` (port stripped), falling back to the first `X-Forwarded-For` entry. This is safe **only because** the ALB rejects requests without `X-Origin-Verify`, which a comment will say. Tests updated |
| `lore/api/main.py` | If `load_on_start == "if_empty"` and `org_kettle` has no `Service` nodes, run the loader in a background thread with progress logs. Never blocks `/api/health`. Unit test with the fake graph |
| `lore/loader/load.py` | Pass a 30 s timeout on its write queries (C5) |
| `backend/Dockerfile` | Already a single uvicorn worker (checked: no `--workers`). Pin a uv image tag that exists for arm64 (the current `ghcr.io/astral-sh/uv:0.11` tag is unverified) |
| `frontend/src/api/client.ts` | `VITE_API_BASE ?? "http://localhost:8000"`, so an empty string means same origin |
| `docker-compose.yml` | Remove the `caddy` service and the `prod` profile; switch to `falkordb-server:v4.18.3` with the same command as ECS. Delete `Caddyfile` and `frontend/vercel.json`; remove `make deploy` (VM rsync) |
| Docs | RUNBOOK §8–9, PROJECT_CONTEXT (layout, env, settings, architecture), DECISIONS D-14/15/16, HUMAN_REVIEW R-12/R-13/R-25, PENDING (T-30..32 replaced), STATE, README (Quickstart deploy + question 6), `infra/README.md` (beginner guide, cost, teardown) |

## 7. Validation (before asking you to deploy)

- `uv run --with cfn-lint cfn-lint infra/cfn/*.yaml` clean.
- `aws cloudformation validate-template` for each file. Your credentials work, and this creates nothing.
- `bash -n infra/deploy.sh` and `shellcheck` (if you install it).
- Backend `ruff` + `pytest` green (274 unit; 296 with `make db-lite`). Frontend `npm run build` + `npm run lint` clean.
- **No `deploy.sh deploy` and no AWS resource creation.** You run it.

## 8. Cost (ap-south-1, ARM64, approximate)

| Item | $/day |
|---|---|
| Fargate ARM 1 vCPU + 2 GB | ~1.10 |
| ALB (hours + light traffic) | ~0.65 |
| Public IPv4 (task + 2 for the ALB) | ~0.36 |
| EFS, Secrets Manager, ECR, logs, SSM | ~0.05 |
| CloudFront + S3 at demo traffic | ~0 (free tier) |
| **Total while running** | **≈ $2.2/day** |
| CodeBuild | ~$0.02–0.05 per build |

**Decision (Ayan, Oct 18): keep it running for at least 30 days.** Infra for 30 days is about **$66**, so the $12/month AWS budget alert will fire around day 5. Raise it (see R-31).

### 8.1 Gemini cost (paid tier, prices from ai.google.dev/gemini-api/docs/pricing, checked Oct 18)

| Model | Input / 1M tokens | Output / 1M tokens (thinking billed as output) | Price change |
|---|---|---|---|
| `gemini-4-argon` (Investigator) | $2.00 | $10.00 | Doubles on **Dec 1 2026** |
| `gemini-3.8-flash` (everything else) | $0.75 | $3.75 | Doubles on **Jan 1 2027** |
| `gemini-embedding-2` (text) | $0.20 | none | |

A 30-day run from Oct 18 ends around Nov 17, so it stays on today's prices.

**Per Story A investigation** (estimated from the code: about 15 Flash calls and 5 Argon calls; prompts ~350 tokens + tool declarations ~450 + growing tool results capped at ~1,500 tokens each):

| | Input tokens | Output tokens | Cost |
|---|---|---|---|
| Flash (Triage, Historian, Responder, report) | ~46k | ~7.5k | ~$0.06 |
| Argon (Investigator) | ~14k | ~7.5k | ~$0.10 |
| **Typical run** | | | **≈ $0.15–0.20** |
| Worst case (Investigator retry + heavy thinking) | | | ≈ $0.40 |

| Other usage | Cost |
|---|---|
| One "Ask the brain" question | ≈ $0.005–0.01 |
| Loading the graph with real embeddings (579 chunks, once; again only after `--reset`) | ≈ $0.02 |
| `make text` (optional, Gemini writes the fake company's text once) | ≈ $0.50 |
| Eval, generation layer: 59 questions × 2 modes | ≈ $1 |
| Eval, investigations: 3 scenarios × 5 runs × 2 modes | ≈ $5–12 |
| Debugging today (~50 investigations) | ≈ $8–20 |

**30-day total, rough:** AWS ≈ $66 + Gemini ≈ $20–40 (development + evals + judges' runs) **≈ $90–110**. The biggest unknown is **strangers on the public URL**: each "Run the 3 AM incident" click costs about $0.20 of Gemini. The per-IP rate limit (20/min) does not cap the total. Options are in R-31.

## 9. Time estimate (deadline: tonight 23:59 IST)

| Step | Time |
|---|---|
| Implementation + validation (agent) | ~2–3 h |
| First deploy (you run it): stacks ~10 min, CodeBuild ~6–8 min, ECS stable ~5 min, CloudFront ~5–15 min, first-boot loader with real embeddings ~2–5 min | ~30–45 min |
| Verify from a phone (SSE through CloudFront, cookie, persona switch, approve → Slack) | ~15 min |

**The biggest risk isn't the infra.** The Gemini side of the app has never run live (PENDING T-03 to T-09). Recommendation: run Story A locally with your new key **in parallel with** the infra work, so prompt or SDK fixes happen while the stacks are being built.

## 10. Still unverified (will be checked during the first deploy)

- Redis actually writes `appendonly`/RDB files to EFS at `/var/lib/falkordb/data`. Check: restart the task, and the graph is still loaded.
- The arm64 build of our image: wheels for every dependency on aarch64, and the uv image tag.
- SSE through CloudFront for a full investigation. The API pings every 15 s (`EventSourceResponse(..., ping=15)` in `api/routes.py`, checked), well inside the 60 s origin read timeout.
- The cookie with `Secure` + `SameSite=Lax` on the CloudFront URL, from a phone.
- `FALKORDB_ARGS` override names (`TIMEOUT_DEFAULT`, `TIMEOUT_MAX`) are accepted by 4.18.3.
- ~~Fargate vCPU quota~~ **Checked Oct 18:** Fargate On-Demand vCPU = 30 (we need 1); ALBs per region = 50; rules per security group = 60 (the CloudFront prefix list uses about 55, so it goes in exactly one rule, as planned).

## 11. Open questions for you

1. ~~OK with C1–C8?~~ **Approved** (Oct 18).
2. ~~`LORE_GITHUB_REPO`?~~ **`ayan2809/kettle-incidents`** (public, exists).
3. ~~After judging: tear down or keep running?~~ **Keep it running for at least 30 days** (R-28). Follow-ups are in **R-31** (still open).
4. ~~Log retention?~~ **3 days** (R-30).
