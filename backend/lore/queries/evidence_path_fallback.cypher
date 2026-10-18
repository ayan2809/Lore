// evidence_path_fallback: same job as evidence_path.cypher, but with plain Cypher shortestPath.
//
// tools.evidence_path runs this only if the algo.SPpaths call raises (for example on a FalkorDB
// build that wants a weight property on every relationship type). Same output columns, same
// permission rule on the suspect PR.
//
// Params: $alert, $pr, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (a:Alert {id: $alert}), (pr:PR {id: $pr})
WHERE pr.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(pr)
MATCH path = shortestPath((a)-[:FIRED_ON|DEPENDS_ON|DEPLOYED_TO|INCLUDES*..6]-(pr))
RETURN [n IN nodes(path) | n.id] AS node_ids,
       [r IN relationships(path) | startNode(r).id] AS rel_sources,
       [r IN relationships(path) | endNode(r).id] AS rel_targets,
       [r IN relationships(path) | type(r)] AS rel_types,
       length(path) AS weight
LIMIT 1
