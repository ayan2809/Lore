// similar_incidents: have we seen something like this before?
//
// 1. Vector search: find the $fetch_k text chunks closest in meaning to the symptom.
// 2. Keep only chunks that belong (PART_OF) to an Incident the viewer is allowed to see.
// 3. Per incident keep its best chunk, then add the services it AFFECTED, the person who
//    RESOLVED_BY it and the PR it was CAUSED_BY (only if the viewer may see that PR).
//
// `score` is a distance (smaller = closer); retrieval.py converts it to a similarity.
// The permission filter is the WHERE on the first MATCH: restricted incidents (for example the
// confidential leaked-key incident) never leave FalkorDB for a viewer without access.
//
// Params: $qvec, $fetch_k, $k, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $fetch_k, vecf32($qvec)) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(inc:Incident)
WHERE inc.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(inc)
WITH viewer, inc, c, score
ORDER BY score ASC
WITH viewer, inc, collect(c)[0] AS best, collect(score)[0] AS score
ORDER BY score ASC
LIMIT $k
OPTIONAL MATCH (inc)-[:AFFECTED]->(s:Service)
WITH viewer, inc, best, score, collect(DISTINCT s.id) AS services
OPTIONAL MATCH (inc)-[:RESOLVED_BY]->(p:Person)
OPTIONAL MATCH (inc)-[:CAUSED_BY]->(pr:PR)
WHERE pr.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(pr)
RETURN inc.id AS id,
       coalesce(inc.name, inc.title) AS title,
       inc.severity AS severity,
       inc.started_at AS started_at,
       inc.access_level AS access_level,
       best.text AS text,
       best.id AS chunk_id,
       score,
       services,
       p.id AS resolved_by,
       pr.id AS caused_by
ORDER BY score ASC
