// ask_entity_facts: what the graph knows about the things a question names (FIX_LOG F-06).
//
// "Who owns pricing?", "Who reviewed PR 482?", "Which team am I on?" are answered by
// relationships, not by any document, so text search alone refuses them. For each named node
// we return its own properties plus its direct relationships (type, direction, the other node).
// This is the graph doing real work in Ask: Graph OFF mode skips it.
//
// Permissions: the node and every neighbour must be visible to the viewer: an org/structure node
// with no access_level ($open_labels), an open level, or a source the viewer is granted through
// a current path. `granted` is collected first, as in graph_neighbourhood, because of the
// FalkorDB 4.18 pattern-predicate quirk (docs/STATE.md C-02).
//
// Python (retrieval.entity_facts) keeps at most a few links per relationship type.
//
// Params: $ids, $open_labels, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
OPTIONAL MATCH (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(g)
WITH collect(DISTINCT g.id) AS granted
MATCH (n)
WHERE n.id IN $ids
WITH granted, n,
     coalesce(n.access_level, CASE WHEN 'Deploy' IN labels(n) THEN 'internal' END) AS level
WITH granted, n, level
WHERE (level IS NULL AND labels(n)[0] IN $open_labels)
   OR level IN $open_levels
   OR n.id IN granted
OPTIONAL MATCH (n)-[r:OWNS|DEPENDS_ON|MEMBER_OF|WAS_MEMBER_OF|HAS_ROLE|AUTHORED|REVIEWED|INCLUDES|DEPLOYED_TO|FIXES|MODIFIES|IMPLEMENTS|SUPERSEDES|AFFECTED|CAUSED_BY|RESOLVED_BY|RECORDED_IN|BUILT_FROM|FIRED_ON]-(m)
WITH granted, n, r, m,
     coalesce(m.access_level, CASE WHEN 'Deploy' IN labels(m) THEN 'internal' END) AS mlevel
WITH granted, n, r, m, mlevel
WHERE m IS NULL
   OR (mlevel IS NULL AND labels(m)[0] IN $open_labels)
   OR mlevel IN $open_levels
   OR m.id IN granted
RETURN n.id AS id,
       labels(n)[0] AS label,
       coalesce(n.name, n.title) AS name,
       n.title AS title,
       n.lead AS lead,
       n.tier AS tier,
       n.status AS status,
       n.access_level AS access_level,
       n.updated_at AS updated_at,
       substring(coalesce(n.text, ''), 0, 600) AS text,
       collect({rel: type(r), outgoing: startNode(r).id = n.id, id: m.id, label: labels(m)[0],
                name: coalesce(m.name, m.title), since: r.since, until: r.to}) AS facts
