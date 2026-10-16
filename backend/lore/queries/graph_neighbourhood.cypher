// graph_neighbourhood: the piece of graph around a node, for the UI canvas.
//
// Walk up to __HOPS__ hops from the centre node over the "knowledge" relationships only (not
// MEMBER_OF / IN_CHANNEL / VISIBLE_TO, which would pull in half the company). Python replaces
// the token __HOPS__ with a whole number 1-3, because FalkorDB does not accept a parameter as
// a path length. Every relationship on those paths becomes one output row: (a)-[type]-(b).
//
// Permissions: a row is kept only if BOTH ends are visible to the viewer. Org-chart nodes have
// no access_level and are always visible; content nodes need an open level or a current
// VISIBLE_TO path; a Deploy counts as "internal". So a restricted thread never appears in the
// graph a viewer is shown, and neither does an edge that points at it.
//
// Why `granted` is collected first: FalkorDB rejects the usual pattern check
// `(viewer)-...-(a)` when `a` comes from startNode(r)/endNode(r) ("Type mismatch: expected Null
// but was Pointer", seen on FalkorDB 4.18.3 via FalkorDBLite on Oct 16). So we list the ids of the
// sources the viewer is granted via a current path once, then test membership with IN.
//
// Params: $center, $limit, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
OPTIONAL MATCH (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(g)
WITH viewer, collect(DISTINCT g.id) AS granted
MATCH (center {id: $center})
MATCH p = (center)-[:DEPENDS_ON|OWNS|BUILT_FROM|CONTAINS|AUTHORED|REVIEWED|MODIFIES|IN_REPO|DEPLOYED_TO|INCLUDES|FIXES|MENTIONS|IMPLEMENTS|DISCUSSED_IN|RECORDED_IN|SUPERSEDES|FIRED_ON|AFFECTED|CAUSED_BY|RESOLVED_BY*1..__HOPS__]-(m)
UNWIND relationships(p) AS r
WITH DISTINCT granted, startNode(r) AS a, type(r) AS rel, endNode(r) AS b
WITH granted, a, rel, b,
     coalesce(a.access_level, CASE WHEN 'Deploy' IN labels(a) THEN 'internal' END) AS a_level,
     coalesce(b.access_level, CASE WHEN 'Deploy' IN labels(b) THEN 'internal' END) AS b_level
WHERE (a_level IS NULL OR a_level IN $open_levels OR a.id IN granted)
  AND (b_level IS NULL OR b_level IN $open_levels OR b.id IN granted)
RETURN a.id AS a_id, labels(a)[0] AS a_label, coalesce(a.name, a.title) AS a_name,
       a.access_level AS a_access, {tier: a.tier, team: a.team, source: a.source} AS a_props,
       rel,
       b.id AS b_id, labels(b)[0] AS b_label, coalesce(b.name, b.title) AS b_name,
       b.access_level AS b_access, {tier: b.tier, team: b.team, source: b.source} AS b_props
LIMIT $limit
