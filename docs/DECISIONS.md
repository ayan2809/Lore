# Design decisions (DECISIONS.md)

A short log of the choices that shape Lore, why we made them, and what we chose not to do. It feeds the README, the blog post and interview answers (plan section 12). Newest entries go at the bottom. **Entries marked "AI-drafted" were written by Claude Code during skeleton scaffolding; Ayan should confirm or rewrite them in his own words.**

| # | Date | Decision | Why | Alternatives rejected |
|---|---|---|---|---|
| D-01 | Oct 12 | **Graph database (FalkorDB) as the single store** for company data, permissions, vectors and agent memory | Root causes are multi-hop connections (alert → service → dependency ← deploy ← PR); permissions are path checks; one store means one query can search, filter and traverse | Vector DB only (can't find the 2-hop cause, proven by Graph OFF eval); Postgres + pgvector (recursive joins, no native path algorithms) |
| D-02 | Oct 12 | **Permission filter inside every Cypher query** (ReBAC) | Restricted content never leaves FalkorDB, so it can't leak into logs, prompts or the UI | Filtering in Python after the query (content already left the DB); asking the model to respect permissions (not a security boundary) |
| D-03 | Oct 12 | **Viewer bound by the server from the session** and merged into query params last (`tools.run_query`) | The model can't impersonate anyone; prompt injection can't widen access | Passing the viewer as a tool argument |
| D-04 | Oct 12 | **Plain Python agent loop + fixed-order Supervisor**, no agent framework | Every line is explainable to judges (rule 12); predictable demo; "smallest abstraction that fits" | LangGraph / CrewAI / Google ADK (ADK kept as fallback) |
| D-05 | Oct 12 | **Facts in code, model narrates.** Severity, blast radius, expertise, conflict resolution are code; Gemini picks tools and writes cited text | Escalation never depends on model mood; facts are testable | Letting the model set severity |
| D-06 | Oct 12 | **Human approval for every outward action**; rollbacks always simulated | FDE "action loop" signal; safety | Auto-posting to Slack |
| D-07 | Oct 12 | **One graph per tenant** (`org_kettle`) using FalkorDB multigraph | Hard isolation between customers, for free | One graph with a tenant property on every node |
| D-08 | Oct 16 | **String `id` property on every node** (`svc:pricing`, `pr:482`) used for citations, UI highlights and MERGE keys | Internal FalkorDB ids can be reused after deletes; readable ids make citations auditable | Internal node ids (AI-drafted) |
| D-09 | Oct 16 | **Cypher in `backend/lore/queries/*.cypher`**, loaded by name | The files are the "documented Cypher" deliverable, and the code runs exactly what is documented | Inline query strings in Python (AI-drafted) |
| D-10 | Oct 16 | **`EXPERT_IN` history kept with `valid_from`/`valid_to`**; access history kept as `WAS_MEMBER_OF` / `WAS_IN_CHANNEL` | "Who owned pricing in March?" still works; only current edges grant access | Overwriting relationships (AI-drafted) |
| D-11 | Oct 16 | **Embedding dimension 768** (`gemini-embedding-001` with `output_dimensionality=768`) | Smaller index, fast enough; the vector index dimension must match `LORE_EMBED_DIM` | 3072 (default) (AI-drafted, verify model id) |
| D-12 | Oct 16 | **Offline-first development**: fake deterministic embeddings, `FakeLLM`, a mock-mode frontend and replay files | Work continues without Docker or a Gemini key; the demo has a fallback if Gemini fails | Requiring live services for every test (AI-drafted) |
| D-13 | Oct 16 | **Source rank** `ADR > runbook > postmortem > ticket > Slack > wiki`; `SUPERSEDES` always wins | Plan section 4 gives ADR > runbook > ticket > Slack; postmortem and wiki were placed by the AI drafter | (AI-drafted, needs Ayan's confirmation: HUMAN_REVIEW) |

## Not automated, on purpose

Rollbacks, paging real people, changing permissions, closing incidents, deciding severity (plan section 4).

## Eval baseline log

| Date | Mode | Retrieval recall@5 | Cited ratio | Leaks | Notes |
|---|---|---|---|---|---|
| (pending) | | | | | First run after the graph is loaded (PENDING_TASKS P0) |

## Rerank weights

Start: `0.5 meaning + 0.2 keyword + 0.2 graph + 0.1 recency` (plan section 8). Record the tuned weights here after the first eval run.
