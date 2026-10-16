// memory_record_finding: an agent's validated finding, linked to the nodes it cites (SUPPORTED_BY).
// Later agents in the same investigation read these instead of passing text around in Python.
MATCH (inv:Investigation {id: $investigation_id})
CREATE (f:Finding {
  id: $id, text: $text, citations: $citations, confidence: $confidence, agent: $agent, ts: $ts
})-[:PART_OF]->(inv)
WITH f
UNWIND $citations AS cid
MATCH (n {id: cid})
CREATE (f)-[:SUPPORTED_BY]->(n)
