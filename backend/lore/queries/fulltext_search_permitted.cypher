// fulltext_search_permitted: search by exact words ("ADR-011", "TTL"), permission-filtered.
//
// Uses the full-text index on Chunk.text (created by the loader). `score` is a relevance
// score here: bigger = better (the opposite of the vector query). The permission filter is the
// same as in vector_search_permitted.cypher. Per source we keep the best chunk.
//
// Params: $text (already cleaned by retrieval.py), $k, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
CALL db.idx.fulltext.queryNodes('Chunk', $text) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(src)
WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)
WITH src, c, score
ORDER BY score DESC
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
ORDER BY score DESC
LIMIT $k
