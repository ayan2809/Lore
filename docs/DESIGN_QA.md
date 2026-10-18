# Lore: design decisions and Q&A

The decisions that shape Lore, and short answers to the questions a reviewer is likely to ask. Each answer points to the file that backs it. The full decision log is in [DECISIONS.md](DECISIONS.md), and every bug found in live testing is in [FIX_LOG.md](FIX_LOG.md).

## Lore in 60 seconds

An alert fires at Kettle, a fictional food-delivery company. Four agents investigate it: Triage, Historian, Investigator and Responder, run in a fixed order by a Supervisor. They work by calling read-only Cypher tools against **one FalkorDB graph**. That graph holds the company (people, teams, services, PRs, deploys, Slack threads, tickets, ADRs, incidents), **who may see what**, the text chunks and their embeddings, and the agents' own memory.

The report names the root-cause PR, rules out the red herring, sets the severity by rule, shows the evidence path and names who to page. Every claim in it cites an id that a tool returned in this run. A human approves anything that leaves the system (a Slack post, a GitHub issue).

## Key design decisions

| # | Decision | Why | Rejected |
|---|---|---|---|
| 1 | FalkorDB is the only store: company data, permissions, vectors and agent memory | Root causes are paths (alert → service → dependency ← deploy ← PR). Keeping access rules in the same graph lets one query search and filter at once | A vector DB + SQL ACL table + a separate memory store |
| 2 | Access is modelled as edges: `VISIBLE_TO` from a restricted source to a Team, Role or Channel; leaving a team turns `MEMBER_OF` into `WAS_MEMBER_OF` | "May Marco still see this?" becomes "does a current path exist?". History is kept, and old edges grant nothing | A permissions table; per-access-level labels |
| 3 | The permission filter is inside every content query, not applied afterwards | Restricted text never leaves FalkorDB, so it can't reach a prompt, a log or the UI | Filtering in Python after retrieval |
| 4 | The viewer comes from the session and is merged into the query parameters *after* the model's arguments ([`tools.run_query`](../backend/lore/tools.py)) | The model can't choose who it is; a prompt injection can't widen access | Passing the viewer as a tool argument |
| 5 | Agents get a fixed catalogue of 11 parameterised tools, each backed by one documented `.cypher` file; tools run with `GRAPH.RO_QUERY` | Predictable, testable, explainable; the database refuses writes even if a check were missed. The free-form `run_cypher` tool was removed (FIX_LOG F-20) | Text-to-Cypher by the model |
| 6 | Facts in code, model narrates: severity, blast radius, who to page and conflict resolution are code; Gemini picks tools and writes cited text | Decisions with a correct answer shouldn't depend on the model. The model once paged the wrong person; it's now a rule (F-03) | Letting the model decide severity and owners |
| 7 | Plain Python agent loop and a fixed-order Supervisor, no agent framework | Every line can be explained; the demo is predictable | LangGraph, CrewAI, ADK |
| 8 | Every tool returns the node ids it touched, the Cypher it ran and the milliseconds | One source for the live graph animation, the audit trail and the citation check | Separate logging |
| 9 | Memory lives in the same graph: Investigation/Step/Finding (episodic), `EXPERT_IN` with `valid_from`/`valid_to` (semantic), Playbook (procedural) | Agents share state through the graph, and a confirmed investigation makes the next one cheaper | An external memory service |
| 10 | Human approval for every outward action; rollbacks are only ever proposals | Safety; Lore advises, people act | Auto-posting, auto-rollback |
| 11 | Graph OFF baseline: same agents and models, vector search only | Proves what the graph's links add, with numbers | Claiming it without a baseline |
| 12 | `gemini-3.8-flash` for the Investigator, `gemini-3.5-flash-lite` for the rest, `gemini-embedding-2` at 768 dims | Measured as accurate as `gemini-4-argon` on Stories A and B, ~1.5× faster and ~45% cheaper (FIX_LOG) | Argon for the Investigator |
| 13 | AWS: one Fargate task with the API and a FalkorDB sidecar, graph on EFS, CloudFront in front; a daily cap of 100 live runs, then recorded runs | Cheapest setup that keeps the graph across restarts; SSE streams for minutes, which rules out Lambda behind API Gateway | Lambda; two tasks writing to one graph |

## Questions and answers

### Rules and the graph's role

**Does the app work without FalkorDB?** No. Every agent tool, the Ask page, the graph view, the permission check, the vector and full-text search and the agents' memory are queries against FalkorDB. Graph OFF is not "without FalkorDB": it still uses FalkorDB's vector index and the same permission check in Cypher. It only stops the agents from following links.

**What does the graph do that vector search can't?** It follows structure: `recent_changes` walks `DEPENDS_ON*0..3` to find a deploy in a *dependency* of the failing service, and `MODIFIES` shows that PR #479 only touched button copy. `evidence_path` uses `algo.SPpaths` from the alert to the PR, and `who_knows` scores experts from `AUTHORED`, `REVIEWED` and `RESOLVED_BY`. On the eval, retrieval recall@5 is 75% with the graph vs 38% without, and plain lookups 93% vs 11%. Ownership and authorship live in edges, not in any document. That was the cause of the Ask page's early 3/12 score (F-06).

**Which FalkorDB features does it use?** Cypher with variable-length paths, `algo.SPpaths`, `algo.pageRank`, the vector index (`db.idx.vector.queryNodes` with `vecf32`), the full-text index, `GRAPH.RO_QUERY`, `GRAPH.COPY` (tests run on a copy of the graph), and multigraph (one graph per tenant, `org_kettle`).

### Graph model and Cypher

**Why string ids like `pr:482`?** Citations, UI highlights and `MERGE` keys need a stable, readable id. FalkorDB's internal ids can be reused after deletes. Every label has an index on `id` ([`loader/indexes.cypher`](../backend/lore/loader/indexes.cypher)).

**How does the permission predicate work?** A source is visible if its `access_level` is open to the viewer, or if a current path exists: `(viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)`. The viewer's open levels come from code ([`permissions.py`](../backend/lore/permissions.py)).

**Vector search filters after the nearest-neighbour step. Doesn't that lose results?** Yes, which is why it over-fetches: 100 chunks before the filter, to keep `k` permitted results ([`vector_search_permitted.cypher`](../backend/lore/queries/vector_search_permitted.cypher)).

**What was the hardest FalkorDB issue?** On 4.18.3, the permission pattern inside `WHERE` failed with "Type mismatch: expected Null but was Pointer" in two shapes: after a `WITH` that computes a new value, and on nodes from `startNode(r)`/`endNode(r)`. It only fires when the pattern is actually evaluated, which is for restricted nodes, so tests on open data passed. The fixes are a pass-through `WITH`, or collecting the viewer's granted ids first and testing with `IN` (STATE C-02, guarded by `test_live_regressions.py`).

**Why is `evidence_path` limited to four relationship types?** So the shortest path is a causal chain (`FIRED_ON`, `DEPENDS_ON`, `DEPLOYED_TO`, `INCLUDES`), not a shortcut through a shared team or channel.

### Security

**Can a prompt make the agent read restricted data?** The model never supplies the viewer, tools are read-only, and every content query filters by the viewer inside FalkorDB. The request policy also blocks attempts to change identity or rules ([`policy.check_request`](../backend/lore/policy.py)). It is keyword-based, a first line only; the guarantees come from the points above.

**How do you know there are no leaks?** The leak test runs 63 probe questions as each of the 4 personas through every tool and search and counts restricted ids in results and citations: 0. It runs in CI against a real FalkorDB container ([`tests/test_permissions_leak.py`](../backend/tests/test_permissions_leak.py)). There are positive controls so the test can't pass by returning nothing.

**Did you ever have a leak?** Yes, found in review. Finding nodes had no `access_level`, a visibility check treated "no level" as public, and a debugging tool returned another persona's findings to the contractor persona. The fix: only org and structure labels count as open, and that tool was later removed (STATE C-12, F-20).

**Can an approved post leak?** A Slack post is blocked if any channel member can't see a cited source. A GitHub issue (a public repo) may not cite restricted or confidential sources. Both are checked in code at approval time and fail closed (F-09).

### Agents and the model

**What does each agent do?** Triage: `find_entity`, `blast_radius`, `service_criticality`. Historian: `similar_incidents`, `get_playbook`, `search_discussions`. Investigator: `recent_changes`, `evidence_path`, `trace_decision`. Responder: `who_knows`, `propose_action`. The Supervisor runs them in that order, sharing a blackboard, and retries the Investigator once if it finds no root cause ([`agents/`](../backend/lore/agents/)).

**How do you stop hallucinated claims?** The final output is parsed into Pydantic. Every claim must cite an id that a tool returned in this run; uncited claims get one retry with the problems listed, then they are dropped and flagged ([`report.py`](../backend/lore/report.py), [`agents/base.py`](../backend/lore/agents/base.py)).

**Why not let the model choose who to page?** It picked the lead of the service that alerted instead of the owner of the service that broke (F-03). Who to page is now a rule: the lead of the team that owns the service the root-cause PR was deployed to.

### Memory

**What is remembered, and how is it used?** Each run writes an Investigation with its Steps and Findings. When a human confirms the root cause, a Playbook is saved. Its steps are chosen by code (the tools whose results contained the cause), and its symptom is written to generalise. On a similar alert, the Investigator gets a step budget equal to the playbook's steps plus one. Story B: 8 → 4 Investigator steps, 50 s → 39 s to the root cause (F-10, F-11).

**Can memory leak across users?** Playbooks store only the symptom, the tool names and the kind of root cause, never tool output. Investigation memory nodes are never treated as open.

### Evaluation and results

**How did you evaluate?** 59 golden questions in five types, asked as different personas, scored deterministically (key facts and source ids present), with no AI judge. Retrieval and generation are measured separately ([`backend/eval/`](../backend/eval/)).

**What didn't meet the target?** Claims with a valid source in the Ask page: 67% against a 90% target. Investigation reports are stricter, because invalid claims are dropped. The data is synthetic, and the Graph ON vs OFF investigation comparison is one recorded run each.

**Graph OFF found the right PR too. So why the graph?** It found PR #482 because the PR's text mentions the TTL. But it needed a second Investigator pass, never examined the red herring, gave no severity, path or owner, and cost $0.091 vs $0.026 and 102 s vs 54 s to the root cause.

### Infrastructure and cost

**What does a run cost, and how is the public URL protected?** Story A costs $0.022–0.027 live. A global cap of 100 live investigations and 1,000 Ask questions per day applies, after which recorded runs are played back, labelled REPLAY. There is also a per-visitor rate limit. CloudFront reaches the API only with a secret origin header.

**Why one Fargate task?** FalkorDB keeps the graph in memory with its files on EFS. Two tasks would mean two writers on one dataset. The cost is about 2 minutes of downtime per backend deploy ([RUNBOOK](RUNBOOK.md) §8.4).

### What would change for production

Real GitHub, Slack and Jira connectors with webhooks; single sign-on, with permissions synced from the source systems; access levels on memory nodes themselves (PENDING T-10); evals on every change that block merges adding a leak; deployment inside the customer's VPC. See the README, section 6.
