// get_playbook: has Lore learned a way to investigate this kind of symptom?
//
// Playbook nodes are written by the memory module after a human confirms a root cause. Each has
// a symptom_pattern, `steps` (a JSON list of tool names), a success_count and an embedding.
// There are only a handful, so we compare the symptom embedding with each one directly using
// vec.cosineDistance (smaller = closer) instead of a vector index. Playbooks that humans
// rejected more often than confirmed (success_count <= 0) are skipped.
//
// Playbooks hold tool names, not company content, so there is no viewer filter.
//
// Params: $qvec, $max_distance, $k
MATCH (p:Playbook)
WHERE p.embedding IS NOT NULL AND coalesce(p.success_count, 0) > 0
WITH p, vec.cosineDistance(p.embedding, vecf32($qvec)) AS distance
WHERE distance <= $max_distance
RETURN p.id AS id,
       p.name AS name,
       p.symptom_pattern AS symptom_pattern,
       p.steps AS steps,
       p.success_count AS success_count,
       distance
ORDER BY distance ASC, success_count DESC
LIMIT $k
