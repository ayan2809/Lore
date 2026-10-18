# Lore runbook: how to operate it

Written so someone other than the author can run Lore. All commands are run from the repo root unless noted. `make help` lists the shortcuts used here.

Settings live in one file, `.env` in the repo root (copy `.env.example`). Every setting starts with `LORE_`.

## 1. Start and stop

Local (laptop):

```bash
make setup      # once: installs Python and Node dependencies
make db         # starts FalkorDB in Docker (needs Docker Desktop)
make api        # API on http://localhost:8000   (separate terminal)
make web        # web page on http://localhost:5173   (separate terminal)
```

Stop: `Ctrl+C` in the API and web terminals, then `make down` (stops the database container, keeps the graph).

**No Docker on this machine?** Use `make db-lite` instead of `make db`. It runs the real FalkorDB module through FalkorDBLite on port 6390 (data in `.falkordb-lite/`, no Browser UI). Put `LORE_FALKORDB_PORT=6390` in `.env`. Stop it with `Ctrl+C`.

Everything in containers locally: `docker compose up -d --build` (database + API). Stop with `docker compose down`. Check with `docker compose ps` and `docker compose logs -f api`. The AWS deployment is separate (section 8).

Quick health check: `curl http://localhost:8000/api/health` should return `falkordb: true`.

Looking at the graph by hand: the compose image (`falkordb/falkordb-server`, the same one AWS runs) has no Browser UI. Use `redis-cli -p 6379 GRAPH.RO_QUERY org_kettle "MATCH (n) RETURN count(n)"`, or, if you want the Browser for a screenshot, run it separately: `docker run -p 3000:3000 -p 6380:6379 falkordb/falkordb` and load into port 6380.

## 2. Reset and reload the graph

The loader uses `MERGE`, so running it twice is safe. `--reset` first deletes the whole graph named by `LORE_GRAPH_NAME`.

```bash
make load-fake   # reload with fake embeddings (no Gemini key; good for tests and CI)
make load        # reload with real Gemini embeddings (needs LORE_GEMINI_API_KEY)
make reset       # nuclear: delete the Docker volume, start an empty database; then run make load
```

**Fake vs real embeddings must match.** After `make load-fake`, set `LORE_FAKE_EMBEDDINGS=true` in `.env` so the API, evals and MCP server embed questions the same fake way. After `make load`, set it back to `false`. Mixing them makes vector search return nonsense without any error.

Investigations, playbooks and feedback live in the same graph, so a reload erases them. Re-record replays afterwards if you need them (section 5).

## 3. Regenerate the data and the text

```bash
make gen    # structured data (people, services, PRs, ...) from the story bible, fixed random seed
make text   # Slack/ticket/ADR wording written by Gemini Flash (needs a key)
make load   # put the result into the graph
```

`make gen` is repeatable: same seed, same output. `make text` calls Gemini, so run it once, check the result by eye, and commit `backend/data/*.json`. That way the demo never changes between runs. If you change a fact in `docs/story-bible.md`, regenerate, reload and re-run the evals.

## 4. Rotate keys

Locally the keys are in `.env`. On AWS they are in one Secrets Manager secret, `lore/app` (section 8.2).

| Secret | Locally | On AWS | How to get a new one |
|---|---|---|---|
| Gemini key | `LORE_GEMINI_API_KEY` in `.env` | key in `lore/app` | Create a new key in Google AI Studio, store it, restart, delete the old key in AI Studio. |
| Slack webhook | `LORE_SLACK_WEBHOOK_URL` | key in `lore/app` | Create a new incoming webhook in the Slack app settings, store it, restart, delete the old webhook. |
| GitHub token | `LORE_GITHUB_TOKEN` | key in `lore/app` | Make a new fine-grained token limited to the demo repo with "Issues: write", store it, restart, revoke the old one. |
| Session secret | `LORE_SESSION_SECRET` | key in `lore/app` (generated) | `openssl rand -hex 32`. Everyone is logged out (they just pick a persona again). |
| FalkorDB password | `LORE_FALKORDB_PASSWORD` in `.env` (optional) | key in `lore/app` (generated) | See the warning below. |

On AWS: `make aws-secrets` (hidden prompts; Enter keeps a stored value; the generated ones are kept too), then `infra/deploy.sh restart` so the running task picks the new values up. To rotate the two generated values (session secret and FalkorDB password) as well, run `infra/deploy.sh secrets --regenerate` (add `--from-env` to read the other three from `.env`).

**Rotating the FalkorDB password on AWS:** the password is applied when the FalkorDB container starts, and the data on EFS does not store it, so a restart with a new value simply works. Both containers read the same key, so they change together.

If a key was ever committed to git, treat it as leaked: rotate it first, then clean the history.

## 5. Gemini quota exhausted or down: replay mode

Replay mode plays back a recorded run instead of calling Gemini. The UI labels it clearly as a replay.

1. In `.env` set `LORE_FORCE_REPLAY=true`.
2. Restart the API (locally `make api`; on AWS change the setting and run `infra/deploy.sh restart`, see section 8.5).
3. Check `curl .../api/health` shows `replay: true`.

Recorded runs are `*.jsonl` files in `backend/replays/` (git-ignored except samples). Record new ones while Gemini works, by running an investigation normally with recording turned on (TODO: confirm the exact switch once `lore/replay.py` is written, and update this line). Set `LORE_FORCE_REPLAY=false` to go back to live runs.

Note that "Ask the brain" and Graph OFF need Gemini too; in replay mode only recorded investigations are available (TODO: confirm).

## 6. Add a persona

A persona is a demo user (Arjun, Dana, Sam, Marco). To add one:

1. `docs/story-bible.md`: add the person, their team, roles and channels, and say what they can and cannot see.
2. `backend/lore/permissions.py`: add an entry to `PERSONAS` with the same `id` as in the story bible.
3. `backend/lore/data_gen/`: make sure the generator creates the `Person` node and the `MEMBER_OF`, `HAS_ROLE` and `IN_CHANNEL` relationships. Then `make gen` and `make load`.
4. Add golden questions for the new persona to `backend/eval/golden.jsonl`, including at least one "should refuse" question.
5. `make test` (the leak test runs for every persona in `PERSONAS`), then `make eval`.
6. The frontend persona switcher reads `GET /api/personas`, so it needs no change.

## 7. Re-run the evals

```bash
make test-all   # unit + integration + leak tests (FalkorDB loaded, Gemini key set)
make eval       # golden questions, Graph ON and OFF, writes backend/eval/report.md
```

`report.md` is git-ignored. Copy the numbers into the README results table by hand (never type a number that is not in the report), and commit the report file deliberately if you want it in the repo (`git add -f`). Evals must always run against a freshly loaded graph (`make load` first), otherwise memory from earlier runs changes the results.

## 8. Deploy to AWS

Everything runs through `infra/deploy.sh` (or the `make aws-*` shortcuts). Region `ap-south-1`, account and user as in `infra/iam/lore-deployer-policy.json`. The architecture, the cost and the reasons for each choice are in `docs/INFRA_PLAN.md` and `infra/README.md`. Nothing here needs Docker on your Mac: the image is built in AWS.

### 8.1 First deploy

```bash
aws sts get-caller-identity            # check you are the deploying user (ayan-mac)
make aws-deploy                        # network + registry stacks, then it STOPS: the secret is not filled yet
make aws-secrets-from-env              # or: make aws-secrets
make aws-deploy                        # image build, app stack, website; prints the public URL
```

After the second `make aws-deploy` finishes (30 to 45 minutes the first time), open the printed `https://dxxxx.cloudfront.net` URL. The API loads the Kettle data into the empty graph in the background on first boot; `make aws-logs` shows `load_on_start_progress` lines, and `/api/health` answers meanwhile (its `falkordb` flag stays `false` until the graph exists).

### 8.2 Secrets

The secret `lore/app` holds five keys: `LORE_GEMINI_API_KEY`, `LORE_SLACK_WEBHOOK_URL`, `LORE_GITHUB_TOKEN`, `LORE_SESSION_SECRET`, `LORE_FALKORDB_PASSWORD`. A second secret, `lore/origin-verify`, holds the CloudFront-to-ALB header value; CloudFormation generates it and `deploy.sh` reads it. CloudFormation creates `lore/app` with `CHANGE_ME` placeholders, and `deploy.sh` refuses to deploy the app until none are left.

| Command | What it does |
|---|---|
| `make aws-secrets` | Generates the session secret and the FalkorDB password (unless already set), and asks for the other three with hidden input. Enter keeps a stored value; Slack and GitHub may be left empty (those actions are then simulated). |
| `make aws-secrets-from-env` | The same, but reads Gemini, Slack and GitHub from the repo-root `.env` (only those three lines are parsed; nothing is echoed). Asks for any that are missing. |

The values go to AWS through a private temp file (mode 0600, deleted on exit). Never edit the secret in a way that puts a value in your shell history. If you prefer the console, sign in as `ayan-mac` (not root) and edit `lore/app` there; do not create it by hand before the stack exists.

### 8.3 Check on it, logs, shell

```bash
make aws-status                        # stacks, task, load balancer target health, URL, /api/health
make aws-logs                          # API logs (follows); make aws-logs CONTAINER=falkordb for the database
infra/deploy.sh exec                   # shell in the api container (ECS Exec; needs the Session Manager plugin)
infra/deploy.sh exec falkordb          # shell in the database container; try: redis-cli -a "$FALKORDB_PASSWORD" GRAPH.LIST
```

Logs are kept 3 days (`/lore/api`, `/lore/falkordb`, `/aws/codebuild/lore-api-build`). Each line from the API is one JSON object (`log_event`).

### 8.4 Ship a change

```bash
git commit ...                         # the image tag is the git sha; uncommitted backend changes get a "-dirty-<time>" tag
make aws-backend                       # zip backend/ -> S3 -> CodeBuild (ARM64) -> ECR -> redeploy the app stack
make aws-frontend                      # npm ci + build (VITE_API_BASE empty) -> S3 -> invalidate /index.html
```

A backend deploy replaces the single task, so the API is down for about 2 minutes (measured on 2026-10-18: old task stopped 15:24:05, new one in the load balancer 15:26:01). During that window the page still loads from S3, but its `/api` calls fail, so the page looks broken. Don't deploy just before a demo. The graph stays on EFS. To try another Gemini model without code changes: `MODEL_PRO=gemini-4-argon infra/deploy.sh backend-only` (also `MODEL_FLASH`, `MODEL_EMBED`, `GITHUB_REPO`, `RATE_LIMIT_PER_MINUTE`; the stack remembers them until you override them again).

### 8.5 Restart and rollback

```bash
infra/deploy.sh restart                # fresh task, same image (after changing a secret or a setting)
infra/deploy.sh rollback               # lists the images in ECR (the last 5 are kept)
infra/deploy.sh rollback <tag>         # redeploys the app stack with that image tag
```

A failed deployment also rolls itself back (ECS deployment circuit breaker).

To switch to replay mode when Gemini is down, set `LORE_FORCE_REPLAY=true` for the task: add `{ Name: LORE_FORCE_REPLAY, Value: "true" }` to the `api` container's `Environment` in `infra/cfn/app.yaml` and run `make aws-backend`. Remove it afterwards.

### 8.6 Tear down

```bash
make aws-destroy                       # type "lore" to confirm
```

It empties the buckets and ECR, deletes the four stacks in reverse order, and force-deletes both secrets so the names are free again. **It deletes the EFS disk, so the graph and all agent memory are lost** (a new deploy reloads the Kettle data). Costs stop. Confirm in the console that no `lore-*` stack, load balancer or CloudFront distribution is left.

## 9. Troubleshooting

**FalkorDB not reachable locally** (`/api/health` shows `falkordb: false`, or "connection refused")
- Is the container up? `docker compose ps`, `docker compose logs falkordb`.
- Docker Desktop not running (Mac)? Start it.
- Running `make api` on the laptop: `LORE_FALKORDB_HOST` must be `localhost`. Inside the compose `api` container it is `falkordb` (compose sets this itself).
- Password mismatch: if FalkorDB has a password, `LORE_FALKORDB_PASSWORD` must match exactly. Errors mention "NOAUTH" or "invalid password".
- Port 6379 already used by another Redis on your laptop: stop it, or change the left side of the port mapping.
- Graph empty after a restart: check that the `falkordb_data` volume is mounted (`docker volume ls`). If it was wiped, run `make load`.
- A brand-new database has no graph yet: `/api/health` shows `falkordb: false` until the first load (FalkorDB refuses to read a graph that does not exist).

**Live steps do not stream (SSE) on the CloudFront URL**
- Symptom: the trail stays empty and everything appears at once at the end, or the stream cuts after about a minute.
- CloudFront must not compress or cache `/api/*`: check the `/api/*` behaviour has `CachingDisabled` and `Compress: false` (`infra/cfn/frontend.yaml`). The API sends an SSE ping every 15 s; the CloudFront origin read timeout is 60 s and the ALB idle timeout is 300 s, so a gap longer than 60 s with no event would cut it.
- Test without the browser: `curl -N https://dxxxx.cloudfront.net/api/investigations/<id>/events` should print events as they happen (start a run first with a session cookie).
- Locally behind another proxy (nginx): `proxy_buffering off;`.

**403 Forbidden from the load balancer** (body just says `Forbidden`)
- Someone called the ALB without the secret header. Normal if you open the ALB address directly: use the CloudFront URL.
- If the CloudFront URL itself returns 403 on `/api/...`, the `X-Origin-Verify` value CloudFront sends differs from the one in the ALB rule. Both stacks take it from the secret `lore/origin-verify`; after anything that regenerated that secret, run `make aws-backend` and `make aws-frontend` so both pick it up. (A 403 XML page on `/` instead means the S3 bucket is empty: run `make aws-frontend`.)

**Task keeps stopping or never becomes healthy** (`make aws-status` shows no running task, or target health `unhealthy`)
- `aws ecs describe-services --cluster lore --services lore-api --query 'services[0].events[:5]'` shows why. Then look at the stopped task: `aws ecs list-tasks --cluster lore --desired-status STOPPED` and `aws ecs describe-tasks ... --query 'tasks[0].stoppedReason'`.
- "ResourceInitializationError ... unable to pull secrets": the secret `lore/app` is missing a key, still unreadable, or the task has no route to the internet (the subnets need a public IP: `AssignPublicIp: ENABLED`).
- "CannotPullContainerError": the image tag is not in ECR (run `make aws-backend`), or Docker Hub refused the FalkorDB pull (rate limit; wait and `infra/deploy.sh restart`).
- The `api` container waits for the `falkordb` health check. If FalkorDB is unhealthy: `make aws-logs CONTAINER=falkordb`. A wrong password in the health check, or EFS not mounted (access point or security group problem), shows up there.
- Healthy only after a while is normal on first boot: the health-check grace period is 180 s.

**Graph is empty on AWS** (`/api/graph` returns nothing, or searches find nothing)
- Look for `load_on_start_*` lines in `make aws-logs`. `load_on_start_skipped` with "no Gemini key" means the secret has no real key; fix it and `infra/deploy.sh restart`. `load_on_start_failed` carries the error.
- Load by hand: `infra/deploy.sh exec`, then `python -m lore.loader.load` (add `--reset` to wipe first).

**Browser calls fail or the persona does not stick on the CloudFront URL**
- The page and the API share one origin, so there is no CORS and the cookie is first-party. The cookie is `HttpOnly; SameSite=Lax; Secure` (`LORE_COOKIE_SECURE=true`). If you opened the page over plain `http://`, CloudFront redirects to HTTPS; use the `https://` URL.
- Locally (page on 5173, API on 8000) the origins differ: `LORE_CORS_ORIGINS` must contain `http://localhost:5173` and `LORE_COOKIE_SECURE` must be `false`.

**`403` or `AccessDenied` from `deploy.sh`**
- The deploying user's policy only allows names starting with `lore-` (roles, buckets) and secrets under `lore/`. Do not rename resources. See `infra/iam/lore-deployer-policy.json`.

**A CloudFormation stack is stuck in `ROLLBACK_COMPLETE`**
- `deploy.sh` deletes it for you and retries. The failure reason is printed; the full event list is in the CloudFormation console.

**Gemini errors (429, quota)**
- Switch to replay mode (section 5). Check billing is enabled in AI Studio.

**Tests fail with connection errors**
- `make test` should never need FalkorDB. If it does, a test is missing the `integration` marker. Integration tests need `make db && make load-fake` first.
