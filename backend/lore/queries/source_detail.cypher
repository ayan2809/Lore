// source_detail: one source (PR, thread, ticket, doc, ADR, incident) with its full text.
//
// Backs GET /api/sources/{id}. The text lives on the source's Chunk nodes (linked by PART_OF),
// returned in chunk-id order. If the viewer may not see the source the query returns no rows and
// the API answers 404, exactly as if it did not exist.
//
// Params: $id, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (src {id: $id})
WHERE labels(src)[0] IN ['PR', 'Thread', 'Ticket', 'Doc', 'Decision', 'Incident']
  AND (src.access_level IN $open_levels
       OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src))
OPTIONAL MATCH (c:Chunk)-[:PART_OF]->(src)
WITH src, c
ORDER BY c.id
RETURN src.id AS id,
       labels(src)[0] AS label,
       src.source AS source,
       coalesce(src.title, src.name) AS title,
       src.updated_at AS updated_at,
       src.access_level AS access_level,
       src.team AS team,
       src.service AS service,
       collect(c.text) AS chunks
