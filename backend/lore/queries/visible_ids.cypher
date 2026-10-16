// visible_ids: of these node ids, which may the viewer see?
//
// Used by the run_cypher safety-net tool to drop any row that mentions an id the viewer must not
// see. Same permission rule as every content query (a Deploy counts as "internal").
//
// A node with no access_level is only visible if it is an org-chart / structure node. Memory and
// trace nodes (Investigation, Step, Finding, Playbook, Action, Query) have no access_level but can
// carry text derived from restricted sources, so they are never visible this way.
//
// Params: $ids, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (n)
WHERE n.id IN $ids
WITH viewer, n, coalesce(n.access_level, CASE WHEN 'Deploy' IN labels(n) THEN 'internal' END) AS level
// Pass-through WITH: works around a FalkorDB 4.18 error on a path pattern in a WHERE attached to
// a WITH that computes a new value (docs/STATE.md C-02).
WITH viewer, n, level
WHERE (level IS NULL
       AND labels(n)[0] IN ['Person', 'Team', 'Role', 'Channel', 'Service', 'Repo', 'CodeModule',
                            'Alert'])
   OR level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(n)
RETURN n.id AS id
