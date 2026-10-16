// memory_record_step: one tool call = one Step node, linked to its investigation and to every
// node the tool returned (TOUCHED). Replaying an investigation = reading its Steps by seq.
// node_ids is a native string array; edges is a JSON string (arrays of maps are not a
// valid property type).
MATCH (inv:Investigation {id: $investigation_id})
CREATE (s:Step {
  id: $id, seq: $seq, agent: $agent, tool: $tool, reason: $reason,
  cypher: $cypher, ms: $ms, node_ids: $node_ids, edges: $edges, error: $error, ts: $ts
})-[:PART_OF]->(inv)
WITH s
UNWIND $node_ids AS nid
MATCH (n {id: nid})
CREATE (s)-[:TOUCHED]->(n)
