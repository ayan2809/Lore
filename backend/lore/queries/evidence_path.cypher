// evidence_path: the shortest chain from the alert to the suspect PR.
//
// algo.SPpaths is FalkorDB's built-in shortest-path algorithm. We allow only four relationship
// types, in either direction, at most 6 hops:
//   alert -FIRED_ON-> service -DEPENDS_ON-> service <-DEPLOYED_TO- deploy -INCLUDES-> PR
// Edge weights come from the `w` property (DEPENDS_ON edges have w = 1). If Day 1 testing shows
// the other types need `w` too, either add it in the loader or use evidence_path_fallback.cypher.
//
// We return plain lists (node ids in order, then the edges as parallel lists) so Python needs no
// graph objects: edge i goes from rel_sources[i] to rel_targets[i] with type rel_types[i].
//
// Permissions: the suspect PR must be visible to the viewer, and the deploy is internal-level.
// The services and the alert in between are org/ops data. If the PR is not visible there is
// simply no row.
//
// Params: $alert (e.g. 'alert:A-3001'), $pr (e.g. 'pr:482'), $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (a:Alert {id: $alert}), (pr:PR {id: $pr})
WHERE pr.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(pr)
CALL algo.SPpaths({sourceNode: a, targetNode: pr,
                   relTypes: ['FIRED_ON', 'DEPENDS_ON', 'DEPLOYED_TO', 'INCLUDES'],
                   weightProp: 'w', relDirection: 'both', maxLen: 6})
YIELD path, pathWeight
RETURN [n IN nodes(path) | n.id] AS node_ids,
       [r IN relationships(path) | startNode(r).id] AS rel_sources,
       [r IN relationships(path) | endNode(r).id] AS rel_targets,
       [r IN relationships(path) | type(r)] AS rel_types,
       pathWeight AS weight
ORDER BY weight ASC
LIMIT 1
