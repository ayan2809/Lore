// memory_feedback: store the human's verdict on the investigation and return the playbooks it used
// and the playbook (if any) already learned from it.
MATCH (inv:Investigation {id: $investigation_id})
SET inv.feedback = $feedback, inv.feedback_at = $ts
WITH inv
OPTIONAL MATCH (inv)-[:USED_PLAYBOOK]->(used:Playbook)
OPTIONAL MATCH (learned:Playbook)-[:LEARNED_FROM]->(inv)
RETURN collect(DISTINCT used.id) AS used, collect(DISTINCT learned.id) AS learned
