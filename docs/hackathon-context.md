# Graph Hacks: Context for AI Agents — Hackathon Context

> **Organizers:** [WeMakeDevs](https://www.wemakedevs.org) × [FalkorDB](https://www.falkordb.com)  
> **Event Portal:** [wemakedevs.org/hackathons/falkordb](https://www.wemakedevs.org/hackathons/falkordb)  
> **Schedule:** [wemakedevs.org/hackathons/falkordb/schedule](https://www.wemakedevs.org/hackathons/falkordb/schedule)  
> **Rules:** [wemakedevs.org/hackathons/falkordb/rules](https://www.wemakedevs.org/hackathons/falkordb/rules)  
> **Resources:** [wemakedevs.org/hackathons/falkordb/resources](https://www.wemakedevs.org/hackathons/falkordb/resources)  
> **Official Discord:** [FalkorDB Discord](https://discord.com/invite/Y2mMT9VdMy) | [WeMakeDevs Discord](https://discord.gg/wemakedevs)

---

## Quick Reference

| Item | Details |
| :--- | :--- |
| **Dates** | **October 15, 2026 (12:01 AM IST) – October 18, 2026 (11:59 PM IST)** |
| **Location** | 100% Online, open worldwide |
| **Eligibility** | Free to enter, developers of all skill levels (no graph DB experience required) |
| **Team Size** | Solo or teams up to 4 members (each person may only join one team) |
| **Mandatory Tech** | **FalkorDB** must be the primary graph database and power a core function |
| **Total Prize Pool** | **$20,000 in total value** (Every member of a winning team receives the prize!) |
| **Tracks** | 3 Tracks (Track 1: Connected Data, Track 2: Memory & Coordination, Track 3: Company Brain) |

---

## 1. Hackathon Overview & Core Challenge

### The Problem
AI agents today often see isolated snippets rather than the full picture. They lose context across sessions, miss structural relationships between people, systems, and data records, and struggle to explain or trace why they took a specific action.

### The Solution: A Graph Context Layer
Graph Hacks challenges participants to build an agent (or multi-agent system) using **FalkorDB** as its contextual backbone. Rather than treating graph data as passive or decorative storage, the graph must actively drive what the agent queries, reasons about, and executes.

### Core Work Expected of the Graph
1. **Follow connections across data** (multi-hop relational reasoning)
2. **Remember across sessions** (persistent episodic, semantic, and procedural memory)
3. **Share state between agents** (coordination, handoffs, shared working memory)
4. **Connect organizational entities** (linking people, code, tickets, documentation, and decisions)
5. **Show transparent reasoning paths** (explainable, auditable agent decision-making)

---

## 2. Schedule & Milestones

The hackathon runs completely online according to Indian Standard Time (IST):

```mermaid
timeline
    title Graph Hacks Schedule (IST)
    Now : Registration Open (Solo or Teams up to 4)
    Oct 15, 12:01 AM IST : Hacking Begins & Submissions Open
    Oct 15 - Oct 18 : 4-Day Hacking Window & Support on Discord
    Oct 18, 11:59 PM IST : Submissions Close & Deadline
```

- **Registration Opens:** Open right now on WeMakeDevs. You can register and add teammates up until the submission deadline.
- **Hacking Begins:** **October 15, 2026 at 12:01 AM IST** — Coding starts, official submissions open.
- **Submissions Close:** **October 18, 2026 at 11:59 PM IST** — Hard deadline for submitting repos, demo videos, and deployments.

---

## 3. Tracks & Prizes

You can submit your project to **one, two, or all three tracks**. When submitting, you must specify every track you are entering.

### 🕵️ Track 01: Agents That Act on Connected Data
* **Goal:** Build an agent that navigates the graph to make decisions and take autonomous actions (e.g., investigating fraud, triaging security vulnerabilities, navigating complex codebases, supply chain analysis).
* **Key Focus Areas:**
  - Multi-hop graph traversal and reasoning
  - Graph queries and graph algorithms exposed as agent tools
  - Tool selection via **Model Context Protocol (MCP)**
  - Action execution driven directly by graph insights
  - Explainable, auditable outputs showing traversal pathways
* **Track Prize:** **iPhone 18 Pro** *(Awarded to EVERY member of the winning team)*

---

### 🤖 Track 02: Agent Memory and Coordination
* **Goal:** Build agents that retain memory across user sessions and coordinate by sharing real-time graph state. Memory must persist, evolve over time, and be accessible across multiple agents.
* **Key Focus Areas:**
  - Episodic, semantic, and procedural memory architectures
  - Persistent conversation histories across sessions
  - Shared state and clean agent-to-agent handoffs
  - High-concurrency reads and writes
  - Isolated, multi-tenant memory per user or agent
* **Track Prize:** **PlayStation 5 (PS5) with GTA VI** *(Awarded to EVERY member of the winning team)*

---

### 🧠 Track 03: Company Brain
* **Goal:** Build an organizational intelligence agent that models how a company operates. Connect people, teams, code repos, docs, Slack/chat logs, Jira/tickets, and architectural decisions into a unified graph.
* **Key Focus Areas:**
  - Unifying unstructured data (docs, tickets, chat) into a single knowledge graph
  - Entity ownership mapping ("Who owns what?" / "Who knows about X?")
  - Decision tracing (linking changes and features back to their original discussions/PRDs)
  - Keeping graph knowledge current as company data mutates
  - Source-grounded answers with direct entity references
* **Track Prize:** **M6 Mac Mini** *(Awarded to EVERY member of the winning team)*

---

### 🎁 Side Prizes
- **Best Blog Post (1 Winner):** **AirPods 5** — Write and publish a comprehensive blog post detailing your project architecture, FalkorDB usage, and learnings.
- **Top 50 Submissions:** **Custom Hackathon T-Shirt** shipped directly to every member of the top 50 teams.

---

## 4. Official Rules & Requirements

All participants agree to the following rules and the WeMakeDevs Code of Conduct:

1. **Team Formation:** Solo or teams of up to 4 members. Each participant can only belong to 1 team.
2. **Mandatory Technology:** FalkorDB must be the primary graph database and power a core feature of the product.
3. **Substantive Graph Usage:** The graph must perform real work. Merely rendering a visual graph UI on top of SQL/relational storage does not qualify. If the app functions without FalkorDB, the project will be disqualified.
4. **Flexible Hosting & Stack:** FalkorDB can be run via Docker, self-hosted, or FalkorDB Cloud. Any programming language (Python, TypeScript/JS, Go, Rust, Java, C#, PHP), UI framework, or backend can be used.
5. **Track Selection:** Open-ended across the three tracks. Teams can enter one, two, or all three tracks, but must explicitly list them in the submission form.
6. **Data Privacy & Licensing:** Only public, synthetic, or your own proprietary data may be used. Do NOT load restricted, private, paywalled, or sensitive personal data into the graph.
7. **Hackathon Window:** October 15, 12:01 AM IST to October 18, 11:59 PM IST.
8. **Original Work:** Main coding and design must take place during the hackathon window. Prior planning (ideation, architecture sketches, graph schema diagrams, notes) is explicitly allowed.
9. **Permitted Third-Party Assets:** Open-source packages, public APIs, templates, starter kits, and foundation models are fully permitted. Judging focuses on original work created during the event.
10. **Submission Deliverables Checklist:**
    - [ ] Public source code repository (GitHub/GitLab)
    - [ ] Comprehensive `README.md` with local setup instructions and graph data model documentation
    - [ ] Documented Cypher queries or graph algorithms used by the system
    - [ ] Video demo showcasing the working application and agent workflow
    - [ ] Live deployment link (or detailed local setup guide if deployment is infeasible)
    - [ ] Specified track name(s)
11. **AI Assistants:** Coding assistants (e.g., Copilot, Cursor, Gemini, Claude) are permitted, but usage must be disclosed.
12. **Technical Mastery:** Team members must understand the code, graph model, Cypher queries, and architecture, and be prepared to defend their technical decisions.
13. **No Low-Effort / Pure AI Slop:** Projects completely generated without meaningful human logic, architectural design, or technical understanding will be disqualified.
14. **Prizes:** Awarded per winning team member.
15. **Intellectual Property:** All IP remains 100% with the participants and teams.
16. **Conduct:** Zero tolerance for harassment, discrimination, plagiarism, or attempting to game judging.

---

## 5. FalkorDB Technical Capabilities & Architecture

FalkorDB is an open-source, in-memory graph database built specifically for low-latency AI agent workloads.

### Key Capabilities
- **Sub-millisecond traversals:** Fast enough to execute complex graph lookups within tight agent inference loops without throttling response latency.
- **Multigraph Topology:** Host thousands of isolated graphs within a single running instance (ideal for multi-tenant memory, per-agent state, or isolated user contexts) without spinning up separate containers.
- **Cypher Query Language:** Standard openCypher support for pattern matching, path finding, aggregations, and mutations.
- **Built-in Graph Algorithms:** Native execution of graph algorithms that agents can invoke as high-level tools:
  - Shortest Path (`algo.shortestPath`)
  - PageRank (`algo.pageRank`)
  - Centrality measures (Betweenness, Degree, Closeness)
  - Connected Components
  - Community Detection (Louvain / Label Propagation)
- **Visual Exploration:** FalkorDB Browser for visual query execution, schema inspection, and debugging.

### Ecosystem & Framework Integrations
- **Model Context Protocol (MCP):** Expose FalkorDB queries and algorithms as standardized tools for Claude, Gemini, and OpenAI-based agentic workflows.
- **GraphRAG-SDK:** Combine vector search with multi-hop knowledge graph retrieval for hallucinations-free agent context.
- **Agent Frameworks:** Official and community integrations with LangChain, LlamaIndex, Cognee, Graphiti, and QueryWeaver.
- **Official Client Libraries:** Python, Node.js / TypeScript, Go, Rust, Java, C#, PHP.

---

## 6. FalkorDB Quickstart

### Running with Docker
```bash
# Pull the latest FalkorDB image
docker pull falkordb/falkordb:latest

# Run FalkorDB locally on port 6379
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
```

### FalkorDB with Docker Compose & Browser
```yaml
version: '3.8'
services:
  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - "6379:6379"
    volumes:
      - falkordb_data:/data
  browser:
    image: falkordb/falkordb-browser:latest
    ports:
      - "3000:3000"
    environment:
      - FALKORDB_HOST=falkordb
      - FALKORDB_PORT=6379
volumes:
  falkordb_data:
```

### Python SDK Example
```python
from falkordb import FalkorDB

# Connect to FalkorDB instance
db = FalkorDB(host='localhost', port=6379)

# Select or create an isolated graph (supports multigraph topology)
graph = db.select_graph('AgentContext')

# Create schema / nodes and edges
graph.query("""
    CREATE (u:User {id: 'usr_123', name: 'Alice'})
    CREATE (p:Project {id: 'prj_456', name: 'Graph Hacks Agent'})
    CREATE (u)-[:CONTRIBUTED_TO {role: 'Lead Architect'}]->(p)
""")

# Query connected context
res = graph.query("""
    MATCH (u:User)-[r:CONTRIBUTED_TO]->(p:Project)
    RETURN u.name AS user, r.role AS role, p.name AS project
""")

for row in res.result_set:
    print(row)
```

### Node.js / TypeScript Example
```typescript
import { FalkorDB } from 'falkordb';

const db = await FalkorDB.connect({
  url: 'redis://localhost:6379'
});

const graph = db.selectGraph('AgentMemory');

await graph.query(`
  MATCH (a:Agent {name: $agentName})-[m:RECALLS]->(fact:Memory)
  RETURN fact.content, fact.timestamp
  ORDER BY fact.timestamp DESC
  LIMIT 10
`, {
  params: { agentName: 'SupervisorAgent' }
});
```

---

## 7. Official Resources & Documentation Links

### Core FalkorDB Documentation
- [Official FalkorDB Documentation](https://docs.falkordb.com)
- [Getting Started Guide](https://docs.falkordb.com/getting-started/)
- [Docker Operations & Setup Guide](https://docs.falkordb.com/operations/docker)
- [FalkorDB Cloud (Managed Hosting)](https://app.falkordb.cloud)
- [FalkorDB Browser Documentation](https://docs.falkordb.com/browser/)
- [The Cypher Query Language Reference](https://docs.falkordb.com/cypher/)
- [Client Libraries Directory](https://docs.falkordb.com/getting-started/clients)
- [Graph Algorithms in FalkorDB](https://docs.falkordb.com/algorithms/)
- [Framework Integrations](https://docs.falkordb.com/integration/)

### Repositories & SDKs
- [FalkorDB Core Engine (GitHub)](https://github.com/FalkorDB/FalkorDB)
- [GraphRAG-SDK (GitHub)](https://github.com/FalkorDB/GraphRAG-SDK)
- [Community Projects & Examples](https://www.falkordb.com/community-projects/)

### Video Tutorials & Playlists
- [Video: How to Write Effective Cypher Queries](https://www.youtube.com/watch?v=emUQmEitSGY)
- [Video: Advanced Graph Algorithms in FalkorDB](https://www.youtube.com/watch?v=aFkgUT0ubYY)
- [YouTube Playlist: Graph & RAG Talks](https://www.youtube.com/playlist?list=PL_SzmSBoVe82kQKf5l_hDxu2yj7FEJDHB)
- [YouTube Playlist: FalkorDB Cloud Setup & Walkthroughs](https://www.youtube.com/playlist?list=PL_SzmSBoVe82pWDPjSDH8QZP6kGxfVjut)

### Communities & Support
- [FalkorDB Discord Server](https://discord.com/invite/Y2mMT9VdMy) (Mentorship, team formation, Q&A)
- [WeMakeDevs Community Discord](https://discord.gg/wemakedevs)
- [WeMakeDevs X / Twitter](https://x.com/WeMakeDevs)
- [WeMakeDevs LinkedIn](https://www.linkedin.com/company/wemakedevs)
- [WeMakeDevs YouTube Channel](https://youtube.com/@WeMakeDevs)
- [WeMakeDevs WhatsApp Channel](https://whatsapp.com/channel/0029Va4vHhJ5Ejxvi1qEBs1F)
- [Support Email](mailto:contact@wemakedevs.org)

---

## 8. Frequently Asked Questions (FAQ)

### When does the hackathon run?
From **October 15, 2026, 12:01 AM IST to October 18, 2026, 11:59 PM IST**. Submissions close promptly at 11:59 PM IST on October 18.

### Who can participate?
The hackathon is open to developers worldwide. You can participate solo or with a team of up to four people.

### Do I need graph database experience?
No. The getting started documentation and the kickoff session cover the basics you need to get up and running.

### Is FalkorDB mandatory?
Yes. FalkorDB must be the primary graph database, and it must support a central part of the product. If the product works identically after taking FalkorDB out, the submission will not qualify.

### Can I enter more than one track?
Yes. You can enter one, two, or all three tracks, and each track has its own distinct prize.
* **Track 01:** An agent that acts on connected data.
* **Track 02:** An agent that remembers across sessions or coordinates between agents.
* **Track 03:** An agent that connects and reasons across company knowledge.

### Where do I register?
Directly on WeMakeDevs at [wemakedevs.org/hackathons/falkordb](https://www.wemakedevs.org/hackathons/falkordb). Sign in or create a free account, then click **Register now**. Your team and submission are managed within that panel.

### Can I use any programming language?
Yes. You may use any language (Python, TypeScript, Go, Rust, Java, etc.), frontend framework, agent framework, or deployment platform.

### Can I continue an existing project?
You may reuse general utility libraries, UI templates, and foundational infrastructure, but the actual submission and its core FalkorDB agent implementation must be newly created during the 4-day hackathon window.

### Can I use AI coding assistants?
Yes (e.g. Cursor, Copilot, ChatGPT, Claude). However, you must disclose their use. Participants must understand their codebase and be ready to explain the architecture, graph schema, Cypher queries, and design choices.

### Does the project need to be deployed?
A live deployment is preferred. Projects that cannot be publicly hosted must provide clear and reproducible local setup instructions and a video demo demonstrating the working system.

