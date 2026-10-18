# Design decisions (DECISIONS.md)

A short log of the choices that shape Lore, why we made them, and what we chose not to do. It feeds the README, the blog post and interview answers (plan section 12). Newest entries go at the bottom. **Entries marked "AI-drafted" were written by Claude Code during skeleton scaffolding; Ayan should confirm or rewrite them in his own words.**

| # | Date | Decision | Why | Alternatives rejected |
|---|---|---|---|---|
| D-01 | Planning | **Graph database (FalkorDB) as the single store** for company data, permissions, vectors and agent memory | Root causes are multi-hop connections (alert → service → dependency ← deploy ← PR); permissions are path checks; one store means one query can search, filter and traverse | Vector DB only (can't find the 2-hop cause, proven by Graph OFF eval); Postgres + pgvector (recursive joins, no native path algorithms) |
| D-02 | Planning | **Permission filter inside every Cypher query** (ReBAC) | Restricted content never leaves FalkorDB, so it can't leak into logs, prompts or the UI | Filtering in Python after the query (content already left the DB); asking the model to respect permissions (not a security boundary) |
| D-03 | Planning | **Viewer bound by the server from the session** and merged into query params last (`tools.run_query`) | The model can't impersonate anyone; prompt injection can't widen access | Passing the viewer as a tool argument |
| D-04 | Planning | **Plain Python agent loop + fixed-order Supervisor**, no agent framework | Every line is explainable to judges (rule 12); predictable demo; "smallest abstraction that fits" | LangGraph / CrewAI / Google ADK (ADK kept as fallback) |
| D-05 | Planning | **Facts in code, model narrates.** Severity, blast radius, expertise, conflict resolution are code; Gemini picks tools and writes cited text | Escalation never depends on model mood; facts are testable | Letting the model set severity |
| D-06 | Planning | **Human approval for every outward action**; rollbacks always simulated | FDE "action loop" signal; safety | Auto-posting to Slack |
| D-07 | Planning | **One graph per tenant** (`org_kettle`) using FalkorDB multigraph | Hard isolation between customers, for free | One graph with a tenant property on every node |
| D-08 | Oct 16 | **String `id` property on every node** (`svc:pricing`, `pr:482`) used for citations, UI highlights and MERGE keys | Internal FalkorDB ids can be reused after deletes; readable ids make citations auditable | Internal node ids (AI-drafted) |
| D-09 | Oct 16 | **Cypher in `backend/lore/queries/*.cypher`**, loaded by name | The files are the "documented Cypher" deliverable, and the code runs exactly what is documented | Inline query strings in Python (AI-drafted) |
| D-10 | Oct 16 | **`EXPERT_IN` history kept with `valid_from`/`valid_to`**; access history kept as `WAS_MEMBER_OF` / `WAS_IN_CHANNEL` | "Who owned pricing in March?" still works; only current edges grant access | Overwriting relationships (AI-drafted) |
| D-11 | Oct 16 | **Embedding dimension 768** (`gemini-embedding-2` with `output_dimensionality=768`) | Smaller index, fast enough; the vector index dimension must match `LORE_EMBED_DIM` | 3072 (default) (AI-drafted, verify model id) |
| D-12 | Oct 16 | **Offline-first development**: fake deterministic embeddings, `FakeLLM`, a mock-mode frontend and replay files | Work continues without Docker or a Gemini key; the demo has a fallback if Gemini fails | Requiring live services for every test (AI-drafted) |
| D-13 | Oct 16 | **Source rank** `ADR > runbook > postmortem > ticket > Slack > wiki`; `SUPERSEDES` always wins | Plan section 4 gives ADR > runbook > ticket > Slack; postmortem and wiki were placed by the AI drafter | (AI-drafted, needs Ayan's confirmation: HUMAN_REVIEW) |
| D-14 | Oct 18 | **ECS Fargate, not Lambda**, for the API | FalkorDB is a long-running server. Investigations stream over SSE for minutes, while API Gateway cuts a response off at about 30 s and Lambda freezes after it responds. The run registry (live investigations) is also in process memory | Lambda + API Gateway (timeouts, no long-lived stream, nowhere to run FalkorDB); App Runner (no EFS, less control); a single EC2 VM (more to patch, no managed load balancer or rollbacks) |
| D-15 | Oct 18 | **One Fargate task = API container + FalkorDB sidecar, graph on EFS** (`DesiredCount 1`, never 2) | The cheapest setup that keeps the graph and the agents' memory across restarts. Containers share localhost, so FalkorDB's port is never opened. One task only: the run registry is in memory, and two FalkorDB processes must never share one EFS folder. A deploy therefore stops the old task before starting the new one (about a minute of downtime) | FalkorDB Cloud or a separate FalkorDB service (extra moving parts, cost, network hop); a second task for the DB (needs service discovery); EBS (not supported on this Fargate setup for persistence across tasks) |
| D-16 | Oct 18 | **Default `*.cloudfront.net` domain, no certificate, no Route 53**; CloudFront to ALB over plain HTTP, guarded by CloudFront's managed IP prefix list plus a secret `X-Origin-Verify` header | No domain to buy or validate, and viewers still get HTTPS. Page and API share one origin, so no CORS and a first-party cookie. The HTTP hop is the known weak spot (not encrypted), accepted for a hackathon demo; the ALB answers 403 to anything without the header | Own domain + ACM certificate + HTTPS to the ALB (more setup, would remove the weak spot); ALB public DNS directly (no HTTPS); Vercel + CORS (cross-site cookies, a second host to explain) |

| D-17 | Oct 18 | **Global daily cap on live Gemini work** (100 investigations, 1,000 Ask questions per UTC day, all visitors together); after the investigation cap, visitors get the recorded run | The public CloudFront URL is open to anyone; the per-IP rate limit slows one visitor but doesn't cap the bill. Worst case ≈ 100 × $0.025 + 1,000 × $0.003 ≈ $5.5/day of Gemini. In-memory counters are exact for one task; a restart resets them | Demo code for judges only (friction for judges); no cap (unbounded cost) |
| D-18 | Oct 18 | **Reasoning model `gemini-3.8-flash`**, light agents `gemini-3.5-flash-lite` | Measured: as accurate as `gemini-4-argon` on Stories A/B, ~1.5× faster, ~45% cheaper (FIX_LOG) | Argon for the Investigator |

## Not automated, on purpose

Rollbacks, paging real people, changing permissions, closing incidents, deciding severity (plan section 4).

## Eval baseline log

| Date | Mode | Retrieval recall@5 | Cited ratio | Leaks | Notes |
|---|---|---|---|---|---|
| Oct 18 | Graph ON | 75% | 67% | 0 | Real gemini-embedding-2; Ask with graph facts; models 3.5-flash-lite / 3.8-flash; key facts 71%, refusals correct 93% |
| Oct 18 | Graph OFF (vector only) | 38% | 49% | 0 | Same questions; key facts 43%, refusals correct 66% |

## Rerank weights

Start: `0.5 meaning + 0.2 keyword + 0.2 graph + 0.1 recency` (plan section 8). Record the tuned weights here after the first eval run.
