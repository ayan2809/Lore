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

Everything in containers (what the VM runs): `docker compose --profile prod up -d --build`. Stop with `docker compose --profile prod down`. Check with `docker compose ps` and `docker compose logs -f api`.

Quick health check: `curl http://localhost:8000/api/health` should return `falkordb: true`.

FalkorDB Browser (to look at the graph and run Cypher by hand): http://localhost:3000.

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

| Secret | Where it lives | How to rotate |
|---|---|---|
| Gemini key | `LORE_GEMINI_API_KEY` in `.env` | Create a new key in Google AI Studio, put it in `.env`, restart the API (`docker compose up -d api` on the VM, which recreates the container with the new env), delete the old key in AI Studio. |
| Slack webhook | `LORE_SLACK_WEBHOOK_URL` | Create a new incoming webhook in the Slack app settings, replace it, restart the API, delete the old webhook. |
| GitHub token | `LORE_GITHUB_TOKEN` | Make a new fine-grained token limited to the demo repo with "Issues: write", replace it, restart, revoke the old token. |
| Session secret | `LORE_SESSION_SECRET` | `openssl rand -hex 32`, replace, restart. Everyone is logged out (they just pick a persona again). |
| FalkorDB password | `LORE_FALKORDB_PASSWORD` in `.env` and `REDIS_ARGS` in `docker-compose.yml` | Change both to the same new value, then `docker compose up -d falkordb api`. |

If a key was ever committed to git, treat it as leaked: rotate it first, then clean the history.

## 5. Gemini quota exhausted or down: replay mode

Replay mode plays back a recorded run instead of calling Gemini. The UI labels it clearly as a replay.

1. In `.env` set `LORE_FORCE_REPLAY=true`.
2. Restart the API (`docker compose up -d api` on the VM, or restart `make api`).
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

## 8. Deploy

### 8.1 Backend on a VM (Docker Compose + Caddy)

One-time setup (TODO(Ayan): choose a provider and host, any small Linux VM with 2 GB RAM or more is enough):

1. Create the VM (Ubuntu). Note its IP address.
2. Install Docker Engine and the compose plugin (follow the official Docker docs for Ubuntu). Check `docker compose version`.
3. Firewall: allow only ports 22, 80 and 443 from the internet. Do NOT open 6379 or 3000.
4. DNS: create an `A` record for your domain (for example `lore.example.com`) pointing at the VM IP. Wait until it resolves.
5. Create `.env` on the VM (from `.env.example`) with at least:
   - `LORE_DOMAIN=lore.example.com`
   - `LORE_GEMINI_API_KEY=...`
   - `LORE_SESSION_SECRET=` a long random value
   - `LORE_FALKORDB_PASSWORD=` a long random value, and the same value in `docker-compose.yml` under `falkordb` -> `environment` -> `REDIS_ARGS: "--requirepass <value>"` (uncomment that block)
   - `LORE_CORS_ORIGINS='["https://<your-vercel-url>"]'`
   - Slack and GitHub settings if you want real actions
6. Copy the repo and start it. From your laptop: `VM_HOST=ubuntu@<ip> make deploy` (rsyncs the code and runs `docker compose --profile prod up -d --build`). Or do it by hand over ssh.
7. Load the graph on the VM: `docker compose exec api python -m lore.loader.load --reset` (add `--fake-embeddings` to skip Gemini).
8. Test: `curl https://lore.example.com/api/health`.

Update later: run `make deploy` again. The graph survives because it is in the `falkordb_data` volume.

Caddy gets and renews the HTTPS certificate by itself the first time the domain is requested. If it cannot (DNS not ready, port 80/443 blocked) see section 9.

### 8.2 Frontend on Vercel

1. Import the GitHub repo in Vercel, set the Root Directory to `frontend`.
2. Framework preset: Vite. Build command `npm run build`, output `dist` (the defaults).
3. Environment variable: `VITE_API_BASE=https://lore.example.com` (no trailing slash). It is baked in at build time, so redeploy after changing it.
4. Add the Vercel URL to `LORE_CORS_ORIGINS` on the VM and restart the API.

## 9. Troubleshooting

**FalkorDB not reachable** (`/api/health` shows `falkordb: false`, or "connection refused")
- Is the container up? `docker compose ps`, `docker compose logs falkordb`.
- Docker Desktop not running (Mac)? Start it.
- Running `make api` on the laptop: `LORE_FALKORDB_HOST` must be `localhost`. Inside the compose `api` container it is `falkordb` (compose sets this itself).
- Password mismatch: if FalkorDB has `--requirepass`, `LORE_FALKORDB_PASSWORD` must match exactly. Errors mention "NOAUTH" or "invalid password".
- Port 6379 already used by another Redis on your laptop: stop it, or change the left side of the port mapping.
- Graph empty after a restart: check that the `falkordb_data` volume is mounted (`docker volume ls`). If it was wiped, run `make load`.

**Live steps do not stream (SSE buffering)**
- Symptom: the trail stays empty and everything appears at once at the end.
- Behind Caddy, `flush_interval -1` in the `Caddyfile` fixes it (already set). Do not add `encode gzip` to that site block.
- Any other proxy or CDN in front (nginx, Cloudflare) can buffer too. For nginx use `proxy_buffering off;`. For Cloudflare turn the orange-cloud proxy off for the API record.
- Test without the browser: `curl -N https://lore.example.com/api/investigations/<id>/events` should print events as they happen.

**CORS errors or "not logged in" after a persona switch**
- The browser blocks calls from the Vercel site to the API unless the API's domain allows it. Check that the exact Vercel origin (scheme + host, no trailing slash) is in `LORE_CORS_ORIGINS`.
- Cookies across sites: when the frontend (`*.vercel.app`) and the API (`lore.example.com`) are on different domains, the session cookie `lore_session` is a third-party cookie. It is only sent if it was set with `SameSite=None; Secure`, and the frontend must make requests with credentials (`fetch(..., { credentials: "include" })`). The API must also answer with `Access-Control-Allow-Credentials: true` and a specific origin (not `*`). `Secure` needs HTTPS, so this cannot work over plain `http://` except on `localhost`.
- If cookies still get blocked (some browsers block third-party cookies entirely), put both under one parent domain (for example `app.example.com` for the web page and `api.example.com` for the API) so the cookie is first-party.
- TODO(Ayan): confirm in `backend/lore/api/` that the cookie is set with these attributes in production, then delete this line.

**Caddy cannot get a certificate**
- `docker compose logs caddy`. Usually DNS does not point at the VM yet, or ports 80/443 are blocked by the cloud firewall.

**Gemini errors (429, quota)**
- Switch to replay mode (section 5). Check billing is enabled in AI Studio.

**Tests fail with connection errors**
- `make test` should never need FalkorDB. If it does, a test is missing the `integration` marker. Integration tests need `make db && make load-fake` first.
