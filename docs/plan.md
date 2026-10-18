# Project "Lore": the company brain that already knows what broke

> **Event:** Graph Hacks (WeMakeDevs × FalkorDB) · Oct 15–18, 2026 (Indian Standard Time) · you are building alone (solo)
> **Tools you'll use:** Python with FastAPI for the server · React for the web page · FalkorDB as the database · Gemini as the AI model
> **Tracks you're entering:** all three: Track 1 (Connected Data), Track 2 (Memory & Coordination) and Track 3 (Company Brain)
> **How it's framed:** the project doubles as a portfolio piece for Forward Deployed Engineer (FDE) jobs. It is closest to "Project 1: permission-aware enterprise knowledge system" from the FDE handout. It also borrows the "action loop" idea from Projects 2 and 5: rules live in code, the AI model explains, and a human approves anything that leaves the system.

### How to read this document

- **Section L** (next) teaches graph databases and FalkorDB from zero. Read it first. Everything after it builds on it.
- **Sections 0 to 21** are the plan itself. They are in the same order as before, with simpler wording and more explanation.
- Nothing about **what** you will build or **when** has changed. Only the explanations got longer and simpler.
- Words in `code style` are names you'll actually type: file names, functions, Cypher keywords or database labels.

### The pitch, in one paragraph

It's 3 AM and the checkout page of a food-delivery app is failing. The engineer on call joined the company 3 weeks ago. They don't know four important things:

1. The checkout service depends on another service called pricing.
2. Yesterday, someone changed a cache setting in pricing.
3. A design decision written 8 months ago warned against exactly that change, and the same thing broke in March.
4. Only one person, Marco, really understands that code.

All of this knowledge exists somewhere: in GitHub, in Slack, in Jira tickets and in people's heads. Nobody can connect it fast enough at 3 AM.

**Lore puts all of it into one FalkorDB graph and sends a team of AI agents to walk through it.** You watch the agents move across the graph live on screen. At the end you get the root cause, the real reason things broke. **Every sentence in the answer points to the source it came from,** and the answer is built only from what **you are allowed to see.**

---

## Section L. Learn first: graph databases and what makes FalkorDB special

This section assumes you've never used a graph database. Read it once before the plan, and come back whenever a word in the plan confuses you.

Facts about FalkorDB in this section come from the FalkorDB documentation you saved as `falkordb_documentation.html`, mainly these pages: Architecture and Design Principles, Atomicity and Concurrency Control, Vector Indexing, Cypher Query Limitations, GRAPH.RO_QUERY, and the main documentation page.

### L.1 What problem does a database solve?

A database is a program that stores data safely and lets you ask questions about it quickly. Different databases are good at different kinds of questions.

- **A relational database** (like Postgres or MySQL) stores data in **tables**, like spreadsheets. Each row is one thing and each column is one fact about it. It is great for questions like "total sales per month".
- **A graph database** stores data as **things and the connections between them**. Think of a whiteboard covered with circles and arrows, or a map of cities and roads. It is great for questions like "how is this thing connected to that thing?"

In Lore, almost every question is a connection question:

- "Which services does checkout depend on, and which of those changed recently?"
- "Who wrote that change, who reviewed it, and which design decision talks about it?"
- "Can Arjun see this Slack thread? Is he in a team or channel that has access?"

That's why the project is built on a graph database.

### L.2 The building blocks of a graph

Here is a tiny piece of Lore's graph drawn as text:

```
(Priya:Person) -[:AUTHORED]-> (PR #482:PR) -[:MODIFIES]-> (pricing/config.yaml:CodeModule)
                                    ^
                                    | [:INCLUDES]
                              (Deploy 991:Deploy) -[:DEPLOYED_TO]-> (pricing:Service)

(checkout:Service) -[:DEPENDS_ON]-> (promo-engine:Service) -[:DEPENDS_ON]-> (pricing:Service)
```

These are the words you need:

| Word | What it means | Example in Lore |
|---|---|---|
| **Node** | One thing. Drawn as a circle. | Priya, PR #482, the pricing service |
| **Relationship** (also called an **edge**) | A named connection between two nodes, drawn as an arrow. | Priya `AUTHORED` PR #482 |
| **Direction** | Every relationship points one way, from a start node to an end node. You can still search in either direction. | `checkout -[:DEPENDS_ON]-> pricing` means checkout needs pricing, not the other way round |
| **Label** | The type of a node. A node can have more than one label. | `Person`, `Service`, `PR` |
| **Relationship type** | The name of a relationship. By convention it's written in CAPITALS. | `DEPENDS_ON`, `AUTHORED` |
| **Property** | A key and value stored on a node or a relationship. | `name: 'pricing'`, `tier: 1`, and on a relationship, `EXPERT_IN {score: 0.9}` |
| **Hop** | One step along one relationship. | checkout → promo-engine is 1 hop; checkout → pricing is 2 hops |
| **Path** | A chain of nodes and relationships. | Alert → checkout → promo-engine → pricing ← Deploy ← PR #482 |
| **Traversal** | Walking the graph hop by hop from a starting point. | What the agents do on screen |

This model of nodes, relationships, labels and properties is called the **property graph model**. FalkorDB uses it.

**The whiteboard test:** if you would explain your data by drawing circles and arrows on a whiteboard, that drawing *is* your graph model. You store it exactly as drawn. There's no need to squeeze it into tables.

### L.3 Why graphs are fast at connection questions

In a table database, connecting data means a **JOIN**: matching rows from one table against rows of another. A question that is 4 hops deep needs 4 joins. A question like "any number of hops" needs a special recursive query. Each join makes the work bigger.

In a graph database the connections are stored directly. Following one is like following a link on a web page, not like searching a whole spreadsheet. A 4-hop question stays fast, because the database only touches the small part of the graph you're walking through.

Here is the same question written both ways: "Which services does checkout depend on, up to 4 hops away?"

In SQL (tables):

```sql
WITH RECURSIVE deps(name, depth) AS (
  SELECT callee, 1 FROM service_deps WHERE caller = 'checkout'
  UNION
  SELECT d.callee, deps.depth + 1
  FROM service_deps d JOIN deps ON d.caller = deps.name
  WHERE deps.depth < 4
)
SELECT DISTINCT name FROM deps;
```

In Cypher (graphs):

```cypher
MATCH (:Service {name: 'checkout'})-[:DEPENDS_ON*1..4]->(dep:Service)
RETURN DISTINCT dep.name
```

Now add "...and the PRs deployed to those services in the last 2 hours, and who wrote them". In SQL that's several more joins. In Cypher you just extend the arrow pattern.

### L.4 Which kind of database for which job

| Kind of database | Best at | Weak at | Used in Lore? |
|---|---|---|---|
| Relational (Postgres, MySQL) | Tables, money transactions, reports, fixed joins | Chasing links when you don't know how deep they go | No |
| Vector store | "Find text that *means* something similar" | Exact facts, connections, order in time | Yes, but as an index *inside* FalkorDB |
| Graph database | Paths, neighbours, influence, "how is X related to Y?" | Big sums over huge flat tables | Yes, the core of everything |

**Use a graph when:**
- your questions are about connections: dependencies, ownership, history, paths, influence;
- you need to explain **why**, because in a graph the path itself is the explanation;
- the shape of your data keeps changing, since adding a new kind of relationship needs no table migration.

**Don't use a graph when:**
- the data is mostly flat records and reports, such as sales per month;
- you only need to search documents by meaning, with no links between them.

### L.5 Cypher in ten minutes

**Cypher** is the language you use to ask a graph database questions. It's the graph version of SQL. You draw the pattern you're looking for with brackets and arrows, and the database finds every place that pattern appears.

- `( )` is a **node**. `(s:Service {name: 'pricing'})` means "a node I'll call `s`, with label `Service`, whose `name` is 'pricing'".
- `-[ ]->` is a **relationship**. `-[:DEPENDS_ON]->` means "a DEPENDS_ON arrow going this way". `-[:MENTIONS]-` with no arrowhead means "either direction".
- `*1..4` on a relationship means "1 to 4 hops of this kind".
- `$name` is a **parameter**: a value your Python code passes in safely, instead of pasting it into the query text.

The words you'll use most:

| Cypher word | What it does | Tiny example |
|---|---|---|
| `MATCH` | Find a pattern | `MATCH (t:Team)-[:OWNS]->(s:Service)` |
| `WHERE` | Filter the results | `WHERE s.tier = 1` |
| `RETURN` | Choose what to give back | `RETURN t.name, s.name` |
| `CREATE` | Always add new data (running it twice makes duplicates) | `CREATE (:Person {name: 'Priya'})` |
| `MERGE` | "Find it, or create it if it's missing" (safe to run twice) | `MERGE (p:Person {id: $id})` |
| `SET` | Change a property | `SET s.tier = 1` |
| `OPTIONAL MATCH` | Like `MATCH`, but keep the row even if nothing is found | finding incidents a service may or may not have |
| `WITH` | Pass results from one part of the query to the next | counting first, then filtering on the count |
| `UNWIND` | Turn a list into rows, used to load many rows in one query | loading 300 PRs at once |
| `ORDER BY ... LIMIT` | Sort and keep the top N | `ORDER BY score DESC LIMIT 5` |

**A good habit:** read queries out loud. `MATCH (p:Person)-[:AUTHORED]->(pr:PR) RETURN p.name` reads as "find a person who authored a PR, and give me the person's name". Judges may ask you to explain your queries (hackathon rule 12), so this matters.

### L.6 Graph algorithms in one paragraph each

Some questions are about the shape of the **whole** graph, not one pattern. For those, FalkorDB has built-in algorithms that you call with `CALL algo.<name>(...)`.

- **BFS (breadth-first search):** spreads out ring by ring from one node. Answers "what can I reach, and how far away is it?" Lore uses this idea for the **blast radius**: everything affected when one service breaks.
- **Shortest path (`algo.SPpaths`):** the GPS route between two nodes. Lore uses it for the **evidence path** from the alert to the guilty PR.
- **PageRank (`algo.pageRank`):** a node is important if important nodes point to it, like how Google first ranked web pages. Lore uses it to rank the most **critical services**.
- **Betweenness centrality (`algo.betweenness`):** finds the bridges, meaning the nodes that sit on many shortest paths. Lore can use it to find people who connect teams.
- **WCC (weakly connected components, `algo.WCC`):** finds islands that aren't connected to anything else. Useful as a data-quality check after loading.
- **CDLP (community detection by label propagation, `algo.CDLP`):** finds groups of nodes that are tightly connected. This powers the optional "Org X-ray" idea.

FalkorDB also has harmonic centrality, A* search, single-source shortest paths (`algo.SSpaths`), maximum flow and minimum spanning forest. Lore doesn't need them.

### L.7 Knowledge graphs and GraphRAG

- A **knowledge graph** is a graph where nodes are real-world things (people, services, decisions) and relationships are facts about them. Lore's "company brain" is a knowledge graph.
- **RAG (retrieval-augmented generation)** means finding relevant text first, then giving it to the AI model so it answers from real sources instead of guessing.
- **GraphRAG** is RAG that also uses the graph. It either follows connections outward from what search found, or uses the graph to narrow down where to search. Lore does both.
- An **embedding** is a list of numbers that represents the meaning of a piece of text. Texts with similar meaning get similar numbers. A **vector index** finds the closest ones quickly. FalkorDB has vector indexes built in, so Lore needs no separate vector database.

### L.8 What makes FalkorDB different from other graph databases

These points come straight from the FalkorDB docs. They are also good talking points with the judges, who are from FalkorDB.

**1. It stores the graph as matrices and walks it with math.**
FalkorDB represents a graph as **sparse adjacency matrices**. Picture a giant grid where row = start node, column = end node, and a 1 means "there's a relationship here". "Sparse" means most cells are empty, so only the filled cells are stored. Each relationship type gets its own matrix (one for `DEPENDS_ON`, one for `AUTHORED`, and so on), plus one matrix for all connections together.

A traversal then becomes **matrix multiplication**. The docs' own example: if F is the "friends" matrix, "friends of friends" is F × F. FalkorDB uses **GraphBLAS**, a standard library for fast sparse-matrix math, to do this. Because multiplication can be reordered, the query planner can choose the cheapest order and run independent parts in parallel.

**2. It lives in memory and is written in C.**
All data is kept in RAM in compact custom structures, with saving to disk for safety. It runs as a native C module inside Redis. The design page reports that it can create over 1 million nodes in under half a second, and 500K relationships in about 0.3 seconds. Results depend on hardware. This is why Lore can run graph queries inside the agent loop without slowing it down.

**3. It speaks the Redis protocol, plus Bolt.**
FalkorDB is a Redis module, so it listens on Redis's port 6379 and you send queries with the commands `GRAPH.QUERY` (read and write) and `GRAPH.RO_QUERY` (read only). It also supports the **Bolt** protocol that Neo4j drivers use. In Python you use the official `falkordb` client, not a generic Redis or Neo4j driver.

**4. Many separate graphs in one server (multigraph).**
One FalkorDB server can hold many graphs, each with its own name. A query on one graph can never see another graph's data. Memory frameworks built on FalkorDB, such as Mem0 and Graphiti, use this to give every user or agent their own isolated graph. Lore uses it for one graph per company (`org_kettle`).

**5. Graph, vector, full-text and range search in one engine.**
- **Vector index:** uses the HNSW algorithm with cosine or euclidean similarity, for vectors of 1 to 4,096 numbers. You create it with `CREATE VECTOR INDEX`, store vectors with `vecf32(...)`, and search with `db.idx.vector.queryNodes`.
- **Full-text index:** keyword search with fuzzy matching. Create it with `db.idx.fulltext.createNodeIndex`.
- **Range index:** fast exact and range lookups on properties such as `name` or `merged_at`.
- **Vector math functions:** `vec.cosineDistance()` and `vec.euclideanDistance()` work inside any query.

Having all of these in one database means one query can search by meaning, filter by permission and follow relationships, all at once.

**6. Built-in graph algorithms.** All the ones in L.6, run inside the database.

**7. Clear rules for many users at once (concurrency).**
- **Reads run in parallel.** Many read queries run at the same time. Each one sees a consistent snapshot of the graph as it was when the read started.
- **Writes take turns.** Write queries on the same graph run one at a time, in arrival order, so they never get mixed up.
- **Every write query is all-or-nothing (atomic).** If anything fails, none of that query's changes are kept.
- **Practical tip from the docs:** batch many changes into one write query instead of many small ones. That's why Lore's loader uses `UNWIND`.
- For several queries that must succeed or fail together, Redis has `MULTI/EXEC` blocks. Lore shouldn't need them.

**8. A real read-only mode.**
`GRAPH.RO_QUERY` (in Python, `graph.ro_query(...)`) refuses any query that tries to write, and it accepts a timeout. This is how Lore guarantees the AI's tools can never change the data.

**9. A Browser for seeing your graph.**
FalkorDB Browser runs at http://localhost:3000. You can type Cypher, see results drawn as a graph, inspect the schema, look at query plans, import CSV files, and use an AI chat panel that turns questions into Cypher.

**10. A growing AI ecosystem.** FalkorDB's GraphRAG SDK, plus integrations with Graphiti, Cognee, Mem0, LangChain, LlamaIndex and MCP (Model Context Protocol).

**Know its history:** FalkorDB is the successor to RedisGraph and was built by the same team. RedisGraph has reached end-of-life. When you search online, ignore RedisGraph-only advice, and don't assume Neo4j-only features exist. FalkorDB supports a **subset** of openCypher, plus its own extensions.

### L.9 Beginner traps the docs warn about

- **Counting with unnamed relationships.** If a relationship in your pattern isn't used anywhere else in the query, FalkorDB only checks that *at least one* exists. That can make counts smaller than you expect. Fix: give the relationship a name and use it, for example `WHERE ID(e) >= 0`.
- **`LIMIT` doesn't stop writes.** `CREATE ... RETURN ... LIMIT 1` still creates every node; only the output is cut short.
- **Indexes don't help `<>` (not equal).** They help with `=`, ranges like `<` and `>`, and text prefixes.
- **No `count()` or `sum()` inside pattern comprehensions** (a pattern written inside square brackets). Count in a `WITH` step first.
- **The `MERGE` duplicate trap.** `MERGE` on a whole pattern creates new copies of every node in it if the full pattern doesn't exist yet. Merge each node first, then merge the relationship between them.

### L.10 How Lore uses each FalkorDB feature

| FalkorDB feature | Where it shows up in Lore |
|---|---|
| Property graph + Cypher | The whole company brain: people, services, PRs, Slack threads, tickets, decisions |
| Multi-hop patterns | Blast radius, recent changes nearby, "who really knows this" |
| `algo.SPpaths` | The evidence path from the alert to PR #482 |
| `algo.pageRank` | Ranking the most critical services |
| Vector index | Finding Slack threads, tickets and docs by meaning, and recalling playbooks |
| Full-text index | Finding exact names like "ADR-011" or "PR-482" |
| Graph + vector in one query | Permission-aware search and graph-scoped search (section 9) |
| Permission paths | "Can this person see this source?" checked inside every query (section 6) |
| `ro_query` | Every agent tool is read-only, so the AI can't change data |
| Multigraph | One graph per company: `org_kettle`, `org_demo2` |
| Reader/writer concurrency | Four agents read at the same time while memory writes queue safely |
| Temporal properties | `valid_from` and `valid_to` on facts, so history is kept, not overwritten |

### L.11 Early answers to your "Day 1 checks"

Section 9 lists four things to verify on Day 1. Your saved docs already hint at some of the answers. **These are notes only; the plan still says to test them on Day 1.**

- **Does `algo.SPpaths` need `weightProp`?** The SPpaths page lists `weightProp` as optional. Still test it; if it fails without one, add `w: 1` to the edges as planned.
- **Does a lower vector `score` mean "closer"?** The vector page calls the score a "distance" measure, which suggests lower = closer, but it doesn't say so outright. Test it with two almost identical sentences.
- **Does the path pattern inside `WHERE` work?** The docs show patterns used inside `WHERE`, for example `WHERE NOT (b)<-[]-()`. Still test your exact permission check.
- **Is there a vector distance function?** Yes: `vec.cosineDistance()` and `vec.euclideanDistance()`. That makes the "filter first, then rank by similarity" option in section 9 possible. Measure its speed on Day 1.

### L.12 Mini glossary

| Term | Meaning |
|---|---|
| Node / relationship / label / property | See L.2 |
| Cypher / openCypher | The graph query language, and its open standard |
| Hop / path / traversal | One step / a chain of steps / walking the graph |
| Index | A lookup structure that makes finding things by a property fast |
| Embedding / vector | A list of numbers that captures the meaning of a text |
| HNSW | The algorithm FalkorDB's vector index uses to find nearby vectors quickly |
| GraphBLAS | The sparse-matrix math library FalkorDB uses for traversals |
| RESP / Bolt | The Redis protocol / the Neo4j protocol; FalkorDB speaks both |
| Multigraph | Many separate named graphs in one server |
| Atomic | All-or-nothing: a write either fully happens or doesn't happen at all |
| Snapshot | The consistent view of the graph a read query sees |
| `ro_query` | Read-only query: any write is refused |
| GraphRAG | Retrieval for AI that uses graph connections, not only text similarity |
| ReBAC | Relationship-based access control: permissions decided by paths in the graph, which is what Lore does |

For deeper beginner explanations with code examples, see the "Graph Hacks Tech Handbook" doc made earlier.

---

## 0. Discovery brief (write this first, before any code)

**What this is:** a one-page description of the customer and their problem. FDE hiring managers want to see that you start from a real problem, not from a cool technology. The company is fictional, and that's fine. What's not fine is being vague.

These numbers are made up for the story. **Keep them identical everywhere: README, video and blog**, so the story stays believable.

| Item | Kettle (a fictional food-delivery startup) |
|---|---|
| **Customer** | Kettle's engineering department: 45 engineers in 6 teams, running about 30 microservices (small programs that each do one job and talk to each other) |
| **Users** | On-call engineers, who take turns each week and many of whom joined in the last 6 months; incident commanders, who lead the response during an outage; engineering managers; and contractors, who have limited access |
| **Current workflow** | An alert fires. The on-call engineer opens a Slack "war room" channel, scrolls through recent GitHub merges and deploy logs, searches Slack and the design decision records (ADRs), asks "who knows pricing?" in #eng, and finally pages whoever the CODEOWNERS file lists |
| **Pain** | It takes a median of **47 minutes** from alert to finding the cause of serious (P1/P2) incidents. **3 of the last 10** incidents paged the wrong person first. Knowledge left with people who changed teams. |
| **Systems involved** | GitHub (PRs, reviews, CODEOWNERS), deploy pipeline logs, Slack (public and private channels), Jira, ADRs and docs, incident history |
| **Constraints** (rules the solution must respect) | 1. People may see only what their access allows: private channels, security incidents and HR are restricted, contractors see public content only, and access changes when someone changes team. 2. Data changes constantly: code merges and deploys land every few minutes. 3. No automatic changes to production: a human approves every action that leaves the system. 4. Only synthetic (made-up) data is allowed (hackathon rule 6). |
| **Success metrics** (how we know it works) | Time from alert to cause **under 3 minutes**. The right owner and expert named the first time. **Zero permission leaks** in the tests. **At least 90%** of statements in answers carry a valid source link. Correct refusals when someone asks about something they can't see. |

## 1. Why this project can win

- **Judges feel the pain.** Every developer has been on call at night or lost in "only one person knows this" knowledge. You don't need to explain the problem; they've lived it.
- **It fits all 3 tracks naturally,** so you can enter all three:
  - **Track 1 (agents acting on connected data):** agents move through service dependencies and code changes, use graph algorithms as tools, take real actions, and are available over MCP.
  - **Track 2 (memory and coordination):** the agents remember past investigations, learn reusable "playbooks", and share one working space inside the graph.
  - **Track 3 (company brain):** people, teams, code, Slack, tickets and design decisions all live in one graph, and answers cite their sources and respect permissions.
- **The graph is clearly required, and you prove it with numbers.** A "Graph OFF" switch turns Lore into plain vector search (text similarity only). In that mode it blames the wrong change. The test harness compares Graph ON vs Graph OFF on the same 50+ questions. This matters because the rules disqualify projects that work just as well without FalkorDB.
- **Permissions are graph-native.** "Can this person see this document?" is really a path question: person → team or channel → document. FalkorDB answers it inside every query (see section 6 and L.10). Few teams will show this.
- **It reads like real FDE work, not a toy demo:** a discovery brief, permissions, tests (evals), failure handling, human approval, and a business number to improve.
- **It looks good on video.** Nodes light up hop by hop, little particles flow along the relationships, and a side panel shows the real Cypher and how many milliseconds it took.
- **Made-up data gives you a controlled demo.** You write the story, so the demo behaves the same way every time.

## 2. What the judges will see (the "wow" moments)

1. **The problem (15 seconds):** "At Kettle it takes 47 minutes to find the cause of an incident, and 3 times in 10 the wrong person gets paged."
2. **An alert fires.** You're logged in as Arjun, this week's on-call engineer. The alert says "checkout p99 latency > 3s", meaning the slowest 1% of checkout requests take over 3 seconds. Four AI agents start working, and the graph lights up as they move through it.
3. **A red herring is dismissed.** A red herring is a clue that looks guilty but isn't. Checkout itself was deployed 12 minutes ago, but that change only edited some text. The agent explains why it's not the cause.
4. **The root cause, with sources.**
   - PR #482 changed the pricing cache time from 300 seconds to 5 seconds, so pricing gets hammered with requests.
   - The evidence path is Alert → checkout → promo-engine → pricing ← Deploy ← PR #482.
   - A design decision record, ADR-011, said never to go below 300 seconds.
   - Every sentence links to the source it came from.
5. **Same question, different person.** The discussion behind ADR-011 happened in the private #pricing-private Slack channel. Arjun can't see that channel, so he gets "1 restricted source matched, ask the Pricing team" and no content. Switch to Dana, the incident commander, and the thread appears as evidence.
6. **Who to call.** Priya wrote the PR. Rahul owns the service on the org chart. Marco is the real expert even though he moved to another team.
7. **Edit, then Approve.** You tweak the Slack message Lore proposed, then approve it. A real Slack post and a real GitHub issue appear.
8. **A failure, on purpose.** The Responder agent tries to quote #pricing-private in the public #incidents post. A check in code blocks it and explains why.
9. **Memory.** "One week later" a similar alert fires on a different service. Lore recalls the playbook it learned last time and solves it in about 4 steps instead of about 11.
10. **The numbers.** A results table: Graph ON vs vector-only on 50+ questions, 0 permission leaks, and time to root cause.

## 3. How it works

```
 Fake company data ("Kettle", a food-delivery startup)
 GitHub PRs · deploys · Slack (public + private channels) · Jira · ADRs · incidents
        │  MERGE loader + Gemini Flash extraction + embeddings + access metadata on every source
        ▼
 ┌────────────────────────── FalkorDB ───────────────────────────┐
 │ graph "org_kettle" = company brain + agent memory + access    │
 │ vector + full-text indexes · algorithms · permission paths    │
 └───────────────────────────────────────────────────────────────┘
        ▲  ~10 read-only Cypher tools, each filtered by the viewer's access
        │  Each returns: data + cypher + ms + node ids (permitted ones only)
        │
 FastAPI (viewer identity from session) ─ Supervisor ─► Triage → Historian → Investigator → Responder
    │  SSE: every step              policy checks in code │ proposals → human edits/approves → Slack, GitHub
    ▼                                                     ▼
 React UI: persona switcher · live graph · trail · cited report      MCP server (same tools) → Gemini CLI

 Eval harness: 50+ golden questions · leak tests · Graph ON vs OFF · latency and cost logs
```

**Reading the diagram from top to bottom:**

1. **Data goes in.** A loader script reads the fake company's data and writes it into FalkorDB using `MERGE`, which is safe to run twice. Gemini Flash, the fast and cheap model, reads Slack and ticket text to find which services and people it mentions. Embeddings are created for search. Every source is tagged with who may see it.
2. **FalkorDB holds everything** in one graph called `org_kettle`: the company data, the agents' memory, and the access rules.
3. **Tools ask the graph questions.** About 10 small, read-only Cypher queries, each wrapped as a Python function the agents can call. Every tool only returns what the current viewer may see.
4. **The server runs the agents.** FastAPI is the Python web server. It knows who is logged in (the "viewer") from the session. The Supervisor runs four agents in order: Triage, then Historian, then Investigator, then Responder.
5. **Steps stream to the browser.** Each step is sent live using SSE (Server-Sent Events, a simple one-way stream from server to browser). Rules in code check every proposed action, and a human edits and approves before anything goes to Slack or GitHub.
6. **The React web page** shows a persona switcher (to log in as different people), the live graph, the trail of reasoning steps, and the final report with sources.
7. **The MCP server** offers the same tools to other AI apps, such as Gemini CLI.
8. **The eval harness** runs 50+ test questions, checks for permission leaks, compares Graph ON vs OFF, and logs speed and cost.

**Three design rules that carry the whole project:**

1. **Every tool returns the piece of the graph it touched:** the node ids, the Cypher it ran, and how long it took. That one rule gives you the live animation, the audit trail and the explanation almost for free.
2. **Permissions are enforced inside the Cypher query.** Content the viewer may not see never leaves FalkorDB, so it can't reach Python, the logs, Gemini or the web page. The viewer's identity comes from the login session, never from the AI model.
3. **Facts are computed in code; the model narrates.** Cypher and Python compute the blast radius, evidence paths, severity and owners. Gemini only picks which tool to use next and explains the results. Every claim it makes must point to an id that a tool actually returned.

## 4. Who decides what: the model, the code, or a human

**Why this matters:** AI models are good at reading and explaining, but they can make mistakes. Anything that must always be right lives in code. Anything risky needs a human. This table makes the split explicit, which is exactly what FDE interviewers look for.

| The model (Gemini) does | The code does | A human does |
|---|---|---|
| Choose the next tool | Filter by permission inside every query | Approve Slack posts, GitHub issues and rollbacks |
| Read Slack, ticket and ADR text | Compute blast radius, paths, PageRank and expertise scores | Edit a proposed message before it goes out |
| Form and rank hypotheses (guesses about the cause) | Set severity by rule (a tier-1 service in the blast radius means P1) | Confirm or reject the root cause, which feeds memory |
| Write the report and answers, with sources | Check every source link, and check that a post's audience may see every cited source | Request or grant access to restricted sources |
| Summarise an investigation into a playbook | Settle conflicts by source rank (ADR > runbook > ticket > Slack; newer beats older) | |

**Deliberately not automated:**
- running rollbacks (undoing a deploy);
- paging real people;
- changing anyone's permissions;
- closing incidents;
- deciding severity.

Severity is a fixed rule in code, so whether an incident escalates never depends on how the model happened to reason that day.

## 5. Graph data model

**What this is:** the list of node types and relationship types Lore stores. It's the "schema" of the graph. If L.2 made sense, this is the same idea applied to the whole company.

| Node | Key properties (the facts stored on it) |
|---|---|
| Person | name, role, joined_at |
| Team, Role, Channel | name (Channel also has `private: true/false`) |
| Service | name, tier (how critical it is; tier 1 is most critical) |
| Repo | name |
| CodeModule | path (e.g. `pricing/config.yaml`) |
| PR | number, title, merged_at |
| Deploy | at, version |
| Ticket | key, title, status |
| Thread (Slack) | channel, text |
| Doc / Decision | title, summary, date |
| Incident / Alert | id, severity, symptom, started_at |
| Chunk | text, embedding (a small piece of text plus its numbers for vector search) |
| Memory: Investigation, Step, Finding, Playbook, Agent | see section 8 |
| Trace: Query | question, viewer, retrieved ids, filtered count, cited ids, ms, tokens, cost |

**Access information stored on every source node (PR, Thread, Ticket, Doc, Incident) and every Chunk:**

```json
{
  "id": "thread:pricing-private-0142",
  "source": "slack",
  "team": "pricing",
  "service": "pricing",
  "updated_at": 1789000000,
  "access_level": "restricted"
}
```

`updated_at` is a Unix timestamp, meaning seconds since 1970. Storing every time as a plain number makes comparisons easy.

**The four access levels:**
- `public`: everyone, including contractors.
- `internal`: all employees, but not contractors.
- `restricted`: only the teams, roles or channels the source points to.
- `confidential`: only people with the security role.

**Main relationship types, grouped:**
- **Organisation:** `MEMBER_OF`, `OWNS`, `HAS_ROLE`, `IN_CHANNEL`. When someone leaves a team, their membership turns into `WAS_MEMBER_OF {from, to}`. That way an access edge always means *current* access.
- **Access:** `VISIBLE_TO`, which points from a restricted or confidential source to the Team, Role or Channel allowed to see it.
- **Services and code:** `DEPENDS_ON`, `BUILT_FROM`, `CONTAINS`.
- **Changes:** `AUTHORED`, `REVIEWED`, `MODIFIES`, `IN_REPO`, `DEPLOYED_TO`, `INCLUDES`.
- **Tickets:** `FIXES`.
- **Discussions and decisions:** `MENTIONS`, `POSTED_IN`, `IMPLEMENTS` (from a PR to a Decision), `DISCUSSED_IN`, `RECORDED_IN`, `SUPERSEDES` (a newer document replaces an older one).
- **Incidents:** `FIRED_ON`, `AFFECTED`, `CAUSED_BY`, `RESOLVED_BY`.
- **Learned and memory relationships:** `EXPERT_IN {score, valid_from, valid_to}` and `PART_OF` (links a Chunk to the source it came from).

**Multi-tenancy** (several customers, each fully separated): use one FalkorDB graph per company, such as `org_kettle` and `org_demo2`. This uses FalkorDB's multigraph feature (L.8, point 4). Say so in the README.

## 6. Permissions (the heart of "Project 1")

**In plain words:** different people must get different answers, depending on what they're allowed to see, and nobody may ever see something they shouldn't. Not in the answer, not in the logs, and not even inside the AI model's input.

**Demo personas** (pretend users you can switch between in the web page):

| Persona | Role | Can see |
|---|---|---|
| Arjun | On-call engineer, Checkout team, joined 3 weeks ago | public + internal + Checkout and on-call channels |
| Dana | Incident commander, also has the security role | everything except HR |
| Sam | Contractor | public only |
| Marco | Moved from Pricing to the Data team in August | lost access to #pricing-private when he moved |

**The rule:** a person can see a source if either:
- its access level is open to them (`public` for everyone, `internal` for employees), or
- there is a *current* path in the graph: person → a team, role or channel ← `VISIBLE_TO` ← source.

This is called **relationship-based access control (ReBAC)**. A permission check is literally a graph path check, which is why it suits FalkorDB so well.

**Where the check runs:** inside the same Cypher query as the search. Nothing the viewer can't see ever comes back from FalkorDB.

**How the viewer's identity reaches the tools:** the server attaches `viewer` to every tool call using the logged-in session. Gemini never chooses it and never sees it, so the model cannot pretend to be someone else.

**When access changes:** when Marco moved teams, his `MEMBER_OF` relationship became `WAS_MEMBER_OF`, so his access to #pricing-private ended immediately. A test proves it. This is the FDE handout's suggested "a document becomes inaccessible when a role changes" constraint, and it's already part of your story.

**The restricted-match warning:** when matching content exists that the viewer can't see, Lore says "1 restricted source matched; ask the Pricing team (Rahul) for access", and shows no content. This does reveal that *something* exists. That's a deliberate, documented trade-off, and the warning can be switched off.

**Checking what goes out:** before posting to a Slack channel, code checks that everyone who can read that channel is allowed to see every source the post cites. If not, the post is blocked and the reason is shown.

## 7. The fake company and its planted stories (the most important prep work)

**What this is:** Lore's demo runs on a made-up company. You decide in advance exactly what happened, called "planted stories", so you know what the right answers are and the demo is repeatable.

**Kettle in numbers:** about 30 services, 45 people, 6 teams, 300 PRs, 150 Slack threads (some in private channels), 80 tickets, 15 ADRs (design decision records) and 10 past incidents. All names are fictional, so you're fully within the data rules.

That's 6 kinds of sources (GitHub, deploys, Slack, Jira, ADRs, incidents), comfortably above the handout's "at least 3" bar.

**The planted stories:**

- **Story A, the main incident:** the pricing cache time change, with the checkout deploy as the red herring (section 2). The ADR discussion lives in #pricing-private.
- **Story B, the memory demo:** a week later, a config change in `eta-predictor` breaks `dispatch`. It's the same pattern as Story A on different services, which is what lets the playbook be reused.
- **Story C, "Ask the brain":** the decision trail behind the pricing cache, plus a question about the ledger service where only one person knows the code (a "bus factor" of 1).
- **Story D, conflicting and out-of-date sources:**
  - An old wiki page says "60s TTL is fine". ADR-011 is newer and has a `SUPERSEDES` relationship over the wiki page, and it says 300s.
  - An old runbook (step-by-step instructions) says "page Marco for pricing", but Marco moved teams. The right answer is "page Rahul, consult Marco".
- **Story E, permission traps:**
  - A March security incident (a leaked API key) in the private #sec-incidents channel, marked confidential.
  - Vendor pricing details in #pricing-private.
  - An HR thread about Marco's move that no demo persona should ever see.

Write these stories as plain notes **before** Oct 15, and **draft the 50+ test questions alongside them** (section 10). Planning notes are explicitly allowed before the hackathon. During the hackathon, a script turns the notes into data.

## 8. Agents, tools and memory

**Key words:**
- An **agent** is an AI model running in a loop: it reads the goal, picks a tool, reads the result, and repeats until it can answer.
- A **tool** is a normal Python function the agent is allowed to call. In Lore, most tools run one Cypher query.

**Four agents.** Each one is the same Python loop with a different prompt (instructions) and a different set of tools.

| Agent | Its job | Main tools |
|---|---|---|
| Triage | What's broken, and how bad is it? | `find_entity`, `blast_radius`, `service_criticality` (PageRank). Severity is set by a rule in code. |
| Historian | Have we seen this before? | `similar_incidents`, `get_playbook`, `search_discussions` |
| Investigator | What changed, and why does it matter? | `recent_changes`, `evidence_path` (`algo.SPpaths`), `trace_decision` |
| Responder | Who should we call, and what should we do? | `who_knows`, `propose_action`, then Slack/GitHub after approval |

**How the agents work together:**

- **The Supervisor is plain Python, not an AI.** It runs the agents in a fixed order, with one retry: if the Investigator's confidence is below 0.7, it looks one more hop out. This keeps the demo reliable, and it's the "smallest abstraction that fits" the FDE handout recommends.
- **The agents share their notes through the graph.** Each investigation is an `Investigation` node. Agents write `Finding` nodes linked to their evidence, and each agent starts by reading what the earlier ones wrote. Because this state lives in the graph rather than in program memory, an investigation can pause and resume even after a restart.
- **Every tool has a required `reason` argument.** The model must say *why* it's calling the tool, and that text shows in the on-screen trail. The `viewer` argument is added by the server and is invisible to the model.
- **Answers come in a fixed, checked format.** The final report follows a Pydantic schema (a strict format checked by Python): `claims: [{text, citations: [ids]}]`. A validator in code checks that every cited id was returned by a tool during this run, and that the viewer may see it. Uncited or invalid claims get one retry; after that they're dropped and flagged.
- **Human in the loop.** Actions start as `Action {status: 'proposed'}`. A human can edit the text, then approve or reject it. Nothing leaves the system without that click.
- **Safety net for free-form questions.** If a question doesn't fit any tool, Gemini may write its own Cypher. It runs through `ro_query` (read-only), with a forced `LIMIT` and the viewer filter.

**"Ask the brain": the question-answering pipeline (the Project 1 core)**

When someone types a question, it goes through five stages:

1. **Hybrid retrieval.** Search three ways at once, each with the permission filter inside the query:
   - vector search, by meaning;
   - full-text search, by keywords;
   - graph-scoped search, limited to what's connected to the topic.
2. **Rerank in code with a score you can explain:** `0.5 × meaning + 0.2 × keyword + 0.2 × graph closeness + 0.1 × recency`. Tune the weights using the test questions, and write the final weights down in DECISIONS.md.
3. **Settle conflicts by rule,** using source rank and `SUPERSEDES` relationships. When two sources disagree, show both.
4. **Generate.** Gemini writes the answer with source links, in the fixed format.
5. **Check the sources,** then save a `Query` trace node so every question can be audited later.

**Memory (Track 2).** Three kinds, like human memory:

- **Episodic, "what happened":** every tool call is saved as a `Step` node with its Cypher, its timing and the nodes it touched. You can replay any past investigation step by step.
- **Semantic, "what's true":** `EXPERT_IN` relationships carry a score and `valid_from`/`valid_to` dates. Old facts get an end date instead of being deleted, so "Who owned pricing in March?" still works.
- **Procedural, "how to do it":** when a human confirms a root cause, Gemini turns the steps into a `Playbook` node. Next time the Historian finds it and the Supervisor runs those tools first. That's where the 11 → 4 step improvement comes from.
- **Feedback:** ✅ or ❌ on a root cause raises or lowers the playbook's `success_count`, so good playbooks rise and bad ones sink.

## 9. Key Cypher queries

These go in `queries/*.cypher` files that the code loads directly, so they also serve as the "documented Cypher" the submission requires. Each one has a plain-English explanation underneath.

```cypher
// Permission-aware retrieval: content the viewer can't see never leaves FalkorDB
MATCH (viewer:Person {id: $viewer})
CALL db.idx.vector.queryNodes('Chunk', 'embedding', 100, vecf32($qvec)) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(src)
WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)
RETURN src.id, src.source, src.updated_at, c.text, score
ORDER BY score LIMIT 10
```
*In plain English:* find the viewer, then find the 100 text chunks closest in meaning to the question. For each chunk, find the source it came from, and keep it only if its access level is open to the viewer, or the viewer belongs to a team, role or channel the source is visible to. Return the best 10.

```cypher
// Blast radius: who is affected if this service breaks
MATCH p = (s:Service {name: $svc})<-[:DEPENDS_ON*1..4]-(up:Service)
RETURN up.name, min(length(p)) AS hops ORDER BY hops
```
*In plain English:* follow `DEPENDS_ON` arrows *backwards* up to 4 hops, to find every service that depends on this one, and how many hops away it is.

```cypher
// Suspects: recent deploys within 3 hops downstream
MATCH (s:Service {name: $svc})-[:DEPENDS_ON*0..3]->(dep:Service)
MATCH (dep)<-[:DEPLOYED_TO]-(d:Deploy)-[:INCLUDES]->(pr:PR)<-[:AUTHORED]-(a:Person)
WHERE d.at > $since
RETURN DISTINCT dep.name, d.at, pr.number, pr.title, a.name ORDER BY d.at DESC
```
*In plain English:* take the failing service and everything it depends on, up to 3 hops. Find deploys to those services since a given time, the PRs inside each deploy, and who wrote them. Newest first.

```cypher
// Evidence path from the alert to the suspect PR (native algorithm)
MATCH (a:Alert {id: $alert}), (pr:PR {number: $pr})
CALL algo.SPpaths({sourceNode: a, targetNode: pr, relTypes: ['FIRED_ON','DEPENDS_ON','DEPLOYED_TO','INCLUDES'],
                   weightProp: 'w', relDirection: 'both', maxLen: 6})
YIELD path RETURN path
```
*In plain English:* find the shortest chain, at most 6 hops, from the alert to the suspect PR, using only these four relationship types in either direction. That chain is the evidence shown to the user.

```cypher
// Who really knows this service (not just who owns it on the org chart)
MATCH (svc:Service {name: $svc})-[:BUILT_FROM]->(:Repo)<-[:IN_REPO]-(pr:PR)<-[r:AUTHORED|REVIEWED]-(p:Person)
WITH svc, p, sum(CASE type(r) WHEN 'AUTHORED' THEN 3 ELSE 1 END) AS codeScore
OPTIONAL MATCH (i:Incident)-[:RESOLVED_BY]->(p) WHERE (i)-[:AFFECTED]->(svc)
RETURN p.name, codeScore + 5 * count(i) AS score ORDER BY score DESC LIMIT 5
```
*In plain English:* for everyone who wrote or reviewed PRs in this service's code repository, give 3 points per PR written and 1 point per PR reviewed. Add 5 points for every past incident on this service they fixed. Show the top 5.

```cypher
// Vector search limited to the graph neighbourhood (add the same viewer filter)
MATCH (:Service {name: $svc})-[:DEPENDS_ON*0..2]-(near:Service)
WITH collect(DISTINCT near) AS nearby
CALL db.idx.vector.queryNodes('Chunk', 'embedding', 50, vecf32($qvec)) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(src)-[:MENTIONS]->(s:Service) WHERE s IN nearby
RETURN DISTINCT src, score ORDER BY score LIMIT 5
```
*In plain English:* collect the services within 2 hops of this one. Search 50 chunks by meaning, and keep only those whose source mentions one of those nearby services. This is "graph-scoped vector search": the vector search finds candidates, and the graph keeps only the connected ones. It's a strong talking point with judges.

```cypher
// Most critical services
CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
RETURN node.name, score ORDER BY score DESC LIMIT 5
```
*In plain English:* run PageRank over services and their dependencies. Services that many important services rely on score highest.

`$open_levels` is worked out in code from the viewer's roles: `['public']` for contractors, `['public', 'internal']` for employees.

**Check on Day 1 morning** (section L.11 has early hints from the docs):
- whether `algo.SPpaths` requires `weightProp` (if so, add `w: 1` to the relationships)
- whether a lower vector `score` means "closer"
- whether the path pattern inside `WHERE` (the permission check) works as written. If not, use `OPTIONAL MATCH` plus `count()`.
- whether FalkorDB has a vector distance function you can use on a permitted set of candidates. That would let you filter **before** the vector search, instead of fetching extra results (k=100) and filtering in the same query.

## 10. Evaluation (how you prove it works)

**What "evaluation" (or "evals") means:** a fixed set of test questions with known right answers. You run Lore on all of them and count how often it's right. This turns "it seems to work" into real numbers, which both judges and FDE interviewers want to see.

**The golden dataset:** at least 50 questions, drafted from the story bible, covering five types and asked as different personas.

| Type | Example (asked as) | What a correct answer looks like |
|---|---|---|
| Easy lookup | "Who owns the pricing service?" (Arjun) | Rahul, citing the team ownership |
| Cross-source synthesis (combining several sources) | "Which PR changed the pricing cache TTL, and which decision covers it?" (Arjun) | PR #482 + ADR-011, both cited |
| Conflicting sources | "What is the minimum safe pricing cache TTL?" (Arjun) | 300s from ADR-011; flags the replaced wiki page |
| Out-of-date information | "Who should I page for pricing?" (Arjun) | Rahul; notes that the runbook is out of date and Marco moved |
| Should refuse | "What happened in the March security incident?" (Sam) | Refuses, shows the restricted warning, leaks nothing |

One line of `eval/golden.jsonl` (JSONL is a file with one JSON object per line):

```json
{"id": "q17", "type": "conflicting", "persona": "arjun",
 "question": "What is the minimum safe pricing cache TTL?",
 "expected_sources": ["adr:011", "wiki:pricing-cache"],
 "must_include": ["300"], "should_refuse": false}
```

**Measure each layer separately.** If the search step (retrieval) found the wrong sources, rewriting the prompt won't fix it. Measuring separately tells you where to look.

| Layer | What you measure | Target |
|---|---|---|
| Retrieval (search) | Did the expected sources come back in the top 5, and only allowed ones? | High recall (finds most of the right ones), 0 forbidden ids |
| Generation (the written answer) | Share of claims with a valid source, correct key facts (`must_include`), correct refusals | At least 90% cited |
| Permissions | Restricted ids showing up in any persona's search results or citations | **0, checked as an automatic pytest test** |
| Investigations | Root cause correct across 5 runs × 3 scenarios, red herring rejected, right people named, number of steps, time to cause, cost | Under 3 minutes to the cause |

- **Graph ON vs vector-only:** run the same questions both ways. The comparison table goes in the README and the video.
- **The harness** (the script that runs the tests): `eval/run.py` reads `golden.jsonl` and writes `eval/report.md`. Run it every day from Day 2, and keep a log of what failed and what you changed.
- **Keep it simple:** score answers by checking that the key facts and source ids are present. That's deterministic, so it gives the same result every time. Check about 10 answers by hand. Skip using an AI to grade answers (an "LLM judge") unless you have spare time.

## 11. Failures built in on purpose

**Why:** real systems fail. Showing that you planned for failures, and what happens when they occur, is one of the strongest FDE signals.

| Failure | How you cause it on purpose | What Lore does |
|---|---|---|
| Out-of-date or conflicting source | Story D | Ranks sources by rule, answers from the most trustworthy one, and shows both sources with a "conflict" tag |
| The model returns badly formatted output | A test that feeds broken output, or a format mismatch | Pydantic rejects it; Lore retries once and tells the model what was wrong; otherwise it shows the raw findings with a warning and logs it |
| A tool call takes too long (times out) | Add an artificial delay to the GitHub API or a slow query | Gives up after a set time and retries with increasing waits (backoff). The step shows as failed in the trail, the agent continues with other evidence, and the action stays waiting |
| The user lacks permission | Sam asks about the security incident | Refuses with the restricted warning and who to ask. The trace proves nothing restricted was even fetched. |
| A request breaks policy | "Post the security details to #general", "Roll back prod now", or unrelated requests | Blocked by rules in code, with the reason shown. A rollback is only ever a proposal. |
| Gemini is down or out of quota | Revoke the API key during a test run | Replay mode (plays back a recorded run), clearly labelled |

At least one of these appears in the video. The README's evaluation section shows all of them and what the system did.

## 12. Observability and running it

**What "observability" means:** being able to see what the system did and why, after the fact. It's what makes problems debuggable and costs visible.

- **Structured JSON logs** for every request: viewer, question, tool calls, milliseconds, tokens (the units AI usage is billed in), estimated cost, errors.
- **A summary for each investigation, shown in the web page:** steps, model calls, tokens, cost, total time, and time to root cause. That last one is your business metric.
- **`Query` trace nodes** for every "Ask the brain" question: candidates found, how many were filtered out by permissions, the reranked order, and the ids cited.
- **RUNBOOK.md**, the instructions for operating Lore: start and stop, reset and reload the graph, rotate keys, what to do when quota runs out (switch to replay), add a persona, re-run the evals. Someone else should be able to run Lore without you.
- **DECISIONS.md**, a short log of design decisions: why a graph, why a custom agent loop, why the permission filter lives in Cypher, and what you chose not to automate. It feeds the README, the blog post and your interviews.

## 13. Tech stack

- **FalkorDB:** run with Docker on your laptop, plus FalkorDB Browser (the visual tool at port 3000) for debugging.
- **Backend (server side):** Python 3.12, FastAPI, the `falkordb` client library, `google-genai` (for tool calling, structured output and embeddings), `sse-starlette` for live streaming, and `mcp` (FastMCP) for the MCP server.
- **Agents:** your own small loop on top of Gemini's function calling, with no heavy framework. It's easier to debug, you can explain every line (hackathon rule 12), and choosing the smaller tool is a senior-engineering signal. Google ADK (Agent Development Kit) is the fallback.
- **Models:** the newest Gemini Pro (strongest reasoning) for the Investigator, Flash (fast and cheap) for extraction and summaries, and the Gemini embedding model. Check the exact model ids in AI Studio. **Enable billing**, because free-tier rate limits will hurt during a live demo.
- **Quality:** pytest for the golden-path and leak tests, plus a small custom eval harness (`eval/run.py`).
- **Frontend (the web page):** React + Vite + TypeScript + Tailwind, and `react-force-graph-2d` for the graph (glow, moving particles, auto-zoom). Add a persona switcher. Use the 3D version only for the opening shot.
- **Deploy (putting it online):** one small rented server (a VM) running Docker Compose with FalkorDB, the API and Caddy (which adds HTTPS). The web page goes on Vercel.

## 14. Day-by-day plan

Oct 15–16 are Thursday and Friday. If you have a job, take leave if you can.

**Prep, before Oct 15 (planning only, no project code). In priority order:**
- [ ] **Write the discovery brief** (section 0) as a one-page note.
- [ ] Write the story bible: people, services, dependencies, the facts of Stories A–E, **and who can see what** (personas, channels, access levels).
- [ ] **Draft the 50+ test questions** from the story bible as notes, with the expected sources and answers.
- [ ] Register, join the FalkorDB Discord, and read the rules page for **how projects are judged** and **whether the blog deadline is the same as the project deadline**.
- [ ] Practise Cypher in a throwaway sandbox: try a vector index, `algo.pageRank`, `algo.SPpaths`, and a permission path check inside `WHERE`.
- [ ] Sketch the schema diagram (including the access relationships), a wireframe of the web page with the persona switcher, demo script version 1, and a README skeleton built on the six questions (section 18).
- [ ] Set up accounts: Gemini with billing, a VM, Vercel, a free Slack workspace with an incoming webhook, and a GitHub demo repo for issues.

**Day 1, Thu Oct 15: graph foundation + permissions.**
*Done means: the golden questions are answered correctly from Python, and the leak test passes for every persona.*
- [ ] First 2 hours: test the risky parts first (vector index, SPpaths, `ro_query`, the permission check, a Gemini tool call). If something doesn't work, find the alternative now, not on Day 3.
- [ ] Data generator:
  - structured data from the story bible, with a fixed random seed so it's the same every run, **including personas, channels, roles and access levels**
  - Slack, ticket and ADR text generated with Gemini Flash **once** and saved to `data/*.json`, so the demo never changes
- [ ] Loader (using `MERGE`), extraction for `MENTIONS` relationships, chunking and embeddings, indexes, and the `VISIBLE_TO` and membership relationships.
- [ ] Write `queries/*.cypher`, with the viewer filter in every query that returns content, and `tools.py`, with `viewer` attached by the server.
- [ ] pytest: the golden paths, plus **the leak test** (no persona ever gets a restricted id).
- [ ] Turn the drafted test questions into `eval/golden.jsonl`.
- [ ] Evening: deploy an empty skeleton to the VM. Deploying early avoids last-day surprises.

**Day 2, Fri Oct 16: agents, memory, answers with sources.**
*Done means: Story A runs end to end in the terminal with a report that cites its sources, Story B uses the playbook, and the first eval report exists.*
- [ ] The agent loop, the 4 agents, and the Supervisor, all writing to the shared Investigation node.
- [ ] Rules in code: severity, source ranking for conflicts, and the post-audience check.
- [ ] Structured report with claims and source links, plus the source-checking validator.
- [ ] "Ask the brain": hybrid retrieval → rerank → answer with sources → check sources → `Query` trace.
- [ ] SSE endpoint that streams every step live.
- [ ] Memory: Steps, Findings, playbook creation, a feedback endpoint, `EXPERT_IN` with dates.
- [ ] `eval/run.py`: first run, at least the retrieval layer. Write the starting numbers in DECISIONS.md.
- [ ] Evening: an ugly but working React page that receives the stream.

**Day 3, Sat Oct 17: web page, actions, failure handling.**
*Done means: the full demo works with clicks on your laptop, including one failure case.*
- [ ] Graph canvas with highlighting and particles, plus the reasoning trail with the Cypher and milliseconds. Clicking a step highlights its part of the graph.
- [ ] Persona switcher, clickable source links, and the restricted-match warning.
- [ ] Report card, **edit-then-approve** actions, real Slack and GitHub (the rollback is only simulated).
- [ ] Failure handling: timeouts and retries, the retry for badly formatted output, refusals, the policy blocks.
- [ ] Run summary in the web page (steps, tokens, cost, time to cause).
- [ ] Graph OFF mode, also connected to the eval harness.
- [ ] MCP server: about an hour, because it just wraps `tools.py`. Test it in Gemini CLI.
- [ ] Evening: deploy everything and test it from your phone. Post update #2 if you're building in public.

**Day 4, Sun Oct 18: measure, polish, ship.**
**Stop adding features at 12:00 PM IST.** After that, only fix and finish.
- [ ] Morning:
  - fix bugs
  - **full eval run, Graph ON vs OFF,** with the results table going into the README
  - **record the golden runs as replay files** (the backup if Gemini fails during judging)
  - add a landing page with one big **"▶ Run the 3 AM incident"** button
  - add rate limiting, so strangers can't run up your Gemini bill
- [ ] README (the six questions, section 18), RUNBOOK.md, DECISIONS.md, eval report.
- [ ] 2–5 PM: record the video (section 16). **Submit by about 7 PM IST**, which leaves about 5 hours of buffer before the deadline.
- [ ] Blog post and final build-in-public post, according to the rules.

## 15. If time runs short, cut in this order

**How to use this:** P0 items are the minimum project. Build them first. Only start P1 when P0 works, and only start P2 when P1 works. If you fall behind, drop from the bottom up.

| Priority | What's included |
|---|---|
| **Must have (P0)** | Discovery brief · data + graph with access info · permission-filtered tools for 3 personas and the leak test · Story A investigation with a sourced report · live highlighting · "Ask the brain" with sources · eval harness (50+ questions, Graph ON vs OFF) · 2 failure cases (permission refusal, retry on bad output) · Story B memory · Approve → Slack post · README (six questions) · video |
| **Should have (P1)** | GitHub issue + edit-before-approve · the other failure cases · reranking · run summary (cost and speed) · RUNBOOK and DECISIONS · live data button (showing fresh data arriving) · MCP server · post-audience check |
| **Nice to have (P2)** | 3D intro · "Org X-ray" (CDLP communities) · two-company demo · loading a real public GitHub repo · back-testing on Kettle's 10 past incidents · pause/resume in the web page |

## 16. Video script (about 3 minutes)

**The rule from the FDE handout:** open with the business problem, show the workflow, include one failure case, and leave the architecture diagram to the end. Don't spend the first minute on diagrams.

| Time | What's on screen |
|---|---|
| 0:00 | The problem: Kettle takes 47 minutes to find an incident's cause, and 3 in 10 page the wrong person (over the rotating company graph) |
| 0:15 | The alert fires while logged in as Arjun; agents walk the graph; the red herring is dismissed |
| 1:00 | The root cause with sources; switch to Dana and the restricted thread appears, while Arjun only saw the warning |
| 1:20 | Edit and Approve: the Slack post and GitHub issue appear. **Failure case:** the attempt to quote a private channel in #incidents is blocked |
| 1:45 | One week later: the playbook is recalled, 4 steps vs 11 |
| 2:05 | The numbers: Graph ON vs vector-only on 50+ questions, 0 permission leaks, time to cause |
| 2:30 | Ask the brain: an answer to a conflicting-source question, showing both sources |
| 2:45 | Under the hood: the architecture, real Cypher with sub-millisecond timings, and the same tools working in Gemini CLI via MCP |

## 17. Risks and safety nets

| What could go wrong | What protects you |
|---|---|
| The AI behaves differently on demo day | Fixed Supervisor order, small tool sets, structured output, golden-path tests, replay mode. Use the temperature your Gemini model's guide recommends; Gemini 3 models advise the default of 1.0. |
| Gemini quota runs out or it's slow | Billing enabled, Flash wherever possible, replay files |
| The permission filter leaves too few results for restricted users | Fetch extra results (k=100) in the same query, and check each persona with the test questions |
| A permission bug leaks data | Filter inside Cypher, viewer attached by the server, leak test in pytest, and the source validator as a second check |
| Writing 50+ test questions takes too long | Draft them during prep from the story bible, and make per-persona variations from templates |
| The FDE additions make the scope too big | Follow the cut list. P0 already covers the FDE signals. |
| The graph view looks cluttered | Show only the nearby part of the graph (about 200 nodes), not all 2,500 |
| Deployment surprises on Day 4 | Deploy on Day 1 and redeploy every day |
| Running out of time | Feature freeze at noon Sunday, and the cut list above |

## 18. README: answer the six questions

The FDE handout says a good README answers these six questions, in this order:

1. **Who is the customer?** Kettle's engineering department and its on-call engineers (the discovery brief).
2. **What was broken?** 47 minutes to find a cause, the wrong people paged, and knowledge that was scattered and partly restricted.
3. **What did you build?** Lore: a permission-aware company graph, four agents, answers with sources, and actions behind human approval.
4. **How does it work?** The architecture, the graph data model, the documented Cypher, the "who decides what" table, and how identity, permissions, retries and failures move through the system.
5. **How did you evaluate it?** The golden question set, results per layer, Graph ON vs OFF, 0 leaks, and the failure table with what the system did each time.
6. **What would you change before real production use?**
   - real GitHub, Slack and Jira connections (webhooks, plus backfilling old data);
   - single sign-on, with permissions copied from the source systems and re-checked regularly;
   - removing personal data;
   - keeping audit logs for a set time;
   - running the evals automatically on every change;
   - cost budgets;
   - running inside the customer's own private cloud network (VPC).

Then add the hackathon requirements: how to run it locally, the tracks, the live link, the video, and the AI-assistant disclosure.

## 19. Prepare for judge (and interviewer) questions

- **Why a graph and not a vector database?** The root cause is two hops away and connected through deploys. Similar text doesn't find it, but connections do. The Graph ON vs OFF numbers prove it.
- **How do permissions work, and how do you know nothing leaks?** The filter runs inside every Cypher query, the server attaches the viewer's identity, and a leak test runs for every persona. The source validator is a second line of defence.
- **Why FalkorDB?** Sub-millisecond traversals inside the agent loop, permission paths, vectors and the graph in one database, one graph per customer, and built-in algorithms. Section L.8 has the details behind each.
- **What did you deliberately not automate?** Rollbacks, paging, permission changes, closing incidents and severity decisions (section 4).
- **How did you evaluate it?** 50+ golden questions across 5 types, with search, answers and permissions measured separately.
- **How do you match different names for the same thing (entity resolution)?** A fixed list of known names, plus alias matching and embedding similarity, with a confidence score on each extracted link.
- **Won't memory grow forever?** Investigations get summarised into playbooks, and facts carry validity dates instead of piling up.
- **What would the real-world version look like?** README question 6.
- **What did AI write?** Disclose it honestly. Write the discovery brief, the schema, the permission model, the Cypher and the eval design yourself, and use AI mostly for boilerplate and tests. You must be able to explain every boundary (hackathon rules 11–13).

## 20. Build in public (optional, but it helps with the blog prize)

"Building in public" means posting your progress on LinkedIn or X during the hackathon. It shows how you think, which is what the FDE handout says gets you noticed.

- **Day 1:** the discovery brief and the graph schema, including the permission model.
- **Day 3:** one test failure that forced you to change something, and what you changed.
- **Day 4:** the demo video, plus the blog post (architecture, how you used FalkorDB, what you learned).

## 21. Submission checklist

- [ ] Public code repository
- [ ] README answering the six questions, plus setup, data model and Cypher docs
- [ ] Discovery brief, DECISIONS.md, RUNBOOK.md and the eval report in the repo
- [ ] Video (business problem first, with one failure case)
- [ ] Live link (with the replay fallback)
- [ ] Tracks entered: all three, with a one-line pitch for each
- [ ] AI disclosure
