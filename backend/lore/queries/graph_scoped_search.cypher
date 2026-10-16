// graph_scoped_search: vector search limited to what is connected to a service.
//
// 1. The vector index finds the $fetch_k chunks closest in meaning to the question.
// 2. The graph keeps only chunks whose source MENTIONS (or, for incidents, AFFECTED) a service
//    within 2 DEPENDS_ON hops of $service, in either direction. `hops` is how close it is.
// 3. The viewer filter keeps only sources the viewer may see (same filter as the other searches).
//
// The vector part answers "similar in meaning", the graph part answers "about something nearby":
// that combination is what plain vector search cannot do. Per source we keep the best chunk.
//
// Params: $service, $qvec, $fetch_k, $k, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $fetch_k, vecf32($qvec)) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(src)
WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)
MATCH (src)-[:MENTIONS|AFFECTED]->(s:Service)
MATCH p = (:Service {id: $service})-[:DEPENDS_ON*0..2]-(s)
WITH src, c, score, min(length(p)) AS hops
ORDER BY score ASC
WITH src, collect(c)[0] AS best, collect(score)[0] AS score, min(hops) AS hops
RETURN src.id AS id,
       labels(src)[0] AS label,
       src.source AS source,
       coalesce(src.title, src.name) AS title,
       src.updated_at AS updated_at,
       src.access_level AS access_level,
       src.service AS service,
       best.text AS text,
       best.id AS chunk_id,
       score,
       hops
ORDER BY score ASC
LIMIT $k
