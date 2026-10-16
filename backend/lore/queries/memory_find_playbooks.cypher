// memory_find_playbooks: the playbooks closest in meaning to this symptom.
// There are only a handful of Playbook nodes, so we compare embeddings directly with
// vec.cosineDistance (smaller = closer) instead of needing a vector index. Same approach as
// get_playbook.cypher (the Historian's tool). Playbooks humans rejected more often than they
// confirmed (success_count <= 0) are skipped; ties go to the playbook with more successes.
// Playbooks hold tool names, not company content, so there is no viewer filter.
MATCH (p:Playbook)
WHERE p.embedding IS NOT NULL AND coalesce(p.success_count, 0) > 0
WITH p, vec.cosineDistance(p.embedding, vecf32($vec)) AS distance
RETURN p.id AS id, p.name AS name, p.symptom_pattern AS symptom_pattern,
       p.steps AS steps, p.success_count AS success_count, distance
ORDER BY distance ASC, success_count DESC
LIMIT $k
