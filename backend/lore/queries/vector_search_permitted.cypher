// vector_search_permitted: search by meaning, but only over sources the viewer may see.
//
// Find the $fetch_k chunks closest in meaning to the question, follow PART_OF to the source
// each came from, and keep it only if the source's access level is open to the viewer OR the
// viewer has a CURRENT path  viewer -> team/role/channel <- VISIBLE_TO <- source.
// (WAS_MEMBER_OF and WAS_IN_CHANNEL are different relationship types, so they grant nothing.)
// Per source we keep the best chunk. `score` is a distance (smaller = closer).
//
// Why fetch more than we return: the filter runs AFTER the vector search, so we over-fetch
// ($fetch_k, e.g. 100) to still have $k permitted results left.
//
// Params: $qvec, $fetch_k, $k, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $fetch_k, vecf32($qvec)) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(src)
WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)
WITH src, c, score
ORDER BY score ASC
WITH src, collect(c)[0] AS best, collect(score)[0] AS score
RETURN src.id AS id,
       labels(src)[0] AS label,
       src.source AS source,
       coalesce(src.title, src.name) AS title,
       src.updated_at AS updated_at,
       src.access_level AS access_level,
       src.service AS service,
       best.text AS text,
       best.id AS chunk_id,
       score
ORDER BY score ASC
LIMIT $k
