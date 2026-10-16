// memory_save_playbook: a confirmed investigation becomes a reusable Playbook (an ordered list of
// tool names plus the symptom it fits). The embedding lets the next alert find it by meaning.
// `steps` is stored as a JSON string, the format get_playbook.cypher documents for its readers.
// A new playbook starts with success_count 1 because a human just confirmed it once.
MATCH (inv:Investigation {id: $investigation_id})
MERGE (p:Playbook {id: $id})
SET p.name = $name,
    p.symptom_pattern = $symptom_pattern,
    p.steps = $steps,
    p.embedding = vecf32($embedding),
    p.success_count = coalesce(p.success_count, 1),
    p.created_at = $ts
MERGE (p)-[:LEARNED_FROM]->(inv)
RETURN p.id AS id
