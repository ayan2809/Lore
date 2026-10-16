// memory_read_investigation: input for a playbook: the investigation's symptom, root cause
// and the tools it called, in order.
MATCH (inv:Investigation {id: $investigation_id})
OPTIONAL MATCH (s:Step)-[:PART_OF]->(inv)
WITH inv, s ORDER BY s.seq
RETURN inv.symptom AS symptom, inv.root_cause AS root_cause, collect(s.tool) AS tools
