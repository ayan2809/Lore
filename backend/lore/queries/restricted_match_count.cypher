// restricted_match_count: how many relevant sources exist that this viewer may NOT see?
//
// Same vector search as vector_search_permitted.cypher, but with the permission test turned
// around (NOT): we keep only the chunks whose source the viewer cannot see, and only those
// close enough in meaning to count as a real match ($max_distance, from
// retrieval.RESTRICTED_MAX_DISTANCE).
// We return counts per owning team and the team lead's name, never any content, so the app
// can say "1 restricted source matched; ask the Pricing team (Rahul)".
//
// The owning team is the source's `team` property ("pricing") looked up as 'team:pricing'.
// The lead is the member of that team with the eng-manager role.
//
// Params: $qvec, $fetch_k, $max_distance, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
CALL db.idx.vector.queryNodes('Chunk', 'embedding', $fetch_k, vecf32($qvec)) YIELD node AS c, score
MATCH (c)-[:PART_OF]->(src)
WHERE score <= $max_distance
  AND NOT (src.access_level IN $open_levels
           OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src))
WITH DISTINCT src
OPTIONAL MATCH (t:Team {id: 'team:' + src.team})
OPTIONAL MATCH (lead:Person)-[:MEMBER_OF]->(t)
WHERE (lead)-[:HAS_ROLE]->(:Role {id: 'role:eng-manager'})
RETURN src.team AS team,
       t.name AS team_name,
       lead.name AS lead,
       count(DISTINCT src) AS matches
ORDER BY matches DESC
