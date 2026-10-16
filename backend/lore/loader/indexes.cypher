// Indexes for the Kettle graph. Run by `python -m lore.loader.load` (statements end with ';').
// Creating an index that already exists is an error in FalkorDB; the loader skips those.
//
// Why indexes: MERGE (n:Label {id: ...}) and MATCH (n:Label {id: ...}) look the node up in the
// index instead of scanning every node with that label.

// ---- 1. Range indexes on `id` (every label the loader or the memory module writes)
CREATE INDEX FOR (n:Person) ON (n.id);
CREATE INDEX FOR (n:Team) ON (n.id);
CREATE INDEX FOR (n:Role) ON (n.id);
CREATE INDEX FOR (n:Channel) ON (n.id);
CREATE INDEX FOR (n:Service) ON (n.id);
CREATE INDEX FOR (n:Repo) ON (n.id);
CREATE INDEX FOR (n:CodeModule) ON (n.id);
CREATE INDEX FOR (n:PR) ON (n.id);
CREATE INDEX FOR (n:Deploy) ON (n.id);
CREATE INDEX FOR (n:Ticket) ON (n.id);
CREATE INDEX FOR (n:Thread) ON (n.id);
CREATE INDEX FOR (n:Doc) ON (n.id);
CREATE INDEX FOR (n:Decision) ON (n.id);
CREATE INDEX FOR (n:Incident) ON (n.id);
CREATE INDEX FOR (n:Alert) ON (n.id);
CREATE INDEX FOR (n:Chunk) ON (n.id);
CREATE INDEX FOR (n:Investigation) ON (n.id);
CREATE INDEX FOR (n:Step) ON (n.id);
CREATE INDEX FOR (n:Finding) ON (n.id);
CREATE INDEX FOR (n:Playbook) ON (n.id);
CREATE INDEX FOR (n:Agent) ON (n.id);
CREATE INDEX FOR (n:Action) ON (n.id);
CREATE INDEX FOR (n:Query) ON (n.id);

// ---- 2. Range indexes on other properties the queries filter by (plan section 9)
CREATE INDEX FOR (n:Service) ON (n.name);
CREATE INDEX FOR (n:PR) ON (n.number);
CREATE INDEX FOR (n:Deploy) ON (n.at);

// ---- 3. Full-text indexes (keyword search; the "keyword" part of hybrid retrieval)
CALL db.idx.fulltext.createNodeIndex('Thread', 'title', 'text');
CALL db.idx.fulltext.createNodeIndex('Ticket', 'title', 'text');
CALL db.idx.fulltext.createNodeIndex('Doc', 'title', 'text');
CALL db.idx.fulltext.createNodeIndex('Decision', 'title', 'text');
CALL db.idx.fulltext.createNodeIndex('Incident', 'title', 'text');
CALL db.idx.fulltext.createNodeIndex('PR', 'title', 'text');
CALL db.idx.fulltext.createNodeIndex('Chunk', 'text');

// ---- 4. Vector indexes (meaning search). `dimension` MUST equal settings.embed_dim
// (LORE_EMBED_DIM, default 768). The loader rewrites it to the setting before running, so the
// two cannot drift apart. Cosine similarity; in FalkorDB a LOWER score means CLOSER.
CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding) OPTIONS {dimension: 768, similarityFunction: 'cosine'};
CREATE VECTOR INDEX FOR (p:Playbook) ON (p.embedding) OPTIONS {dimension: 768, similarityFunction: 'cosine'};
