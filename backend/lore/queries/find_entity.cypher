// find_entity: look up a service, person, team, PR, ticket, thread, ADR ... by id or by name.
//
// Matches when the node id equals one of the guesses in $ids (the tool turns "ADR-011" into
// "adr:011", "PR 482" into "pr:482" and so on), or when the name/title contains the text.
// Exact id matches are listed first. For a Service we also return the owning team.
//
// Permissions: org-chart nodes (Service, Person, Team ...) have no access_level, so everyone
// may see them. Content nodes (PR, Thread, Ticket, Doc, Decision, Incident) must pass the
// viewer filter. A Deploy is treated as "internal": contractors do not get it.
//
// Params: $text, $ids (list of id guesses), $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (n)
WHERE labels(n)[0] IN ['Service', 'Person', 'Team', 'Role', 'Channel', 'Repo', 'CodeModule',
                       'PR', 'Deploy', 'Ticket', 'Thread', 'Doc', 'Decision', 'Incident', 'Alert']
  AND (n.id IN $ids
       OR toLower(n.name) CONTAINS toLower($text)
       OR toLower(n.title) CONTAINS toLower($text))
WITH viewer, n,
     coalesce(n.access_level, CASE WHEN 'Deploy' IN labels(n) THEN 'internal' END) AS level
// Pass-through WITH: works around a FalkorDB 4.18 error on a path pattern in a WHERE attached to
// a WITH that computes a new value (docs/STATE.md C-02).
WITH viewer, n, level
WHERE level IS NULL
   OR level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(n)
OPTIONAL MATCH (owner:Team)-[:OWNS]->(n)
RETURN n.id AS id,
       labels(n)[0] AS label,
       coalesce(n.name, n.title) AS name,
       n.tier AS tier,
       n.access_level AS access_level,
       owner.id AS owner_team
ORDER BY CASE WHEN n.id IN $ids THEN 0 ELSE 1 END,
         CASE WHEN labels(n)[0] IN ['Service', 'Team', 'Person'] THEN 0 ELSE 1 END,
         name
LIMIT 10
