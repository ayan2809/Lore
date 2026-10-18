// trace_decision: why is it like this? The decision trail around a service, ADR or PR.
//
// $entity can be a decision id ('adr:011'), a service id ('svc:pricing') or a PR id ('pr:482').
// We find the Decisions (ADRs) that are that entity, are about that service (their `service`
// property), or are IMPLEMENTED by that PR. For each decision we collect:
//   - the Slack threads it was DISCUSSED_IN (only those the viewer may see), with the first
//     300 characters of each as `thread_notes`, so the agent can cite what was discussed,
//   - the older documents it SUPERSEDES and any newer one that supersedes it,
//   - past incidents that AFFECTED the same service, with the postmortem they were RECORDED_IN.
// `hidden_threads` counts discussion threads the viewer may NOT see (count only, no content),
// and `hidden_team` says which team owns them, so the app can show a restricted-match warning.
//
// Permissions: every content node (decision, thread, old/new doc, incident, postmortem) passes
// the viewer filter.
//
// Params: $entity, $entity_short (id without the prefix, e.g. 'pricing'), $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (dec:Decision)
WHERE (dec.id = $entity
       OR dec.service IN [$entity, $entity_short]
       OR (dec)<-[:IMPLEMENTS]-(:PR {id: $entity}))
  AND (dec.access_level IN $open_levels
       OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(dec))
OPTIONAL MATCH (dec)-[:DISCUSSED_IN]->(th:Thread)
WHERE th.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(th)
WITH viewer, dec, collect(DISTINCT th.id) AS threads,
     collect(DISTINCT {id: th.id, gist: substring(th.text, 0, 300)}) AS thread_notes
OPTIONAL MATCH (dec)-[:DISCUSSED_IN]->(hidden:Thread)
WHERE NOT (hidden.access_level IN $open_levels
           OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(hidden))
WITH viewer, dec, threads, thread_notes, count(DISTINCT hidden) AS hidden_threads, collect(DISTINCT hidden.team)[0] AS hidden_team
OPTIONAL MATCH (dec)-[:SUPERSEDES]->(old)
WHERE old.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(old)
WITH viewer, dec, threads, thread_notes, hidden_threads, hidden_team, collect(DISTINCT old.id) AS supersedes
OPTIONAL MATCH (newer)-[:SUPERSEDES]->(dec)
WHERE newer.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(newer)
WITH viewer, dec, threads, thread_notes, hidden_threads, hidden_team, supersedes,
     collect(DISTINCT newer.id) AS superseded_by
OPTIONAL MATCH (inc:Incident)-[:AFFECTED]->(s:Service)
WHERE (s.id = dec.service OR s.name = dec.service)
  AND (inc.access_level IN $open_levels
       OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(inc))
OPTIONAL MATCH (inc)-[:RECORDED_IN]->(pm)
WHERE pm.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(pm)
RETURN dec.id AS decision_id,
       coalesce(dec.title, dec.name) AS title,
       dec.updated_at AS updated_at,
       dec.access_level AS access_level,
       threads,
       thread_notes,
       hidden_threads,
       hidden_team,
       supersedes,
       superseded_by,
       collect(DISTINCT {incident: inc.id, postmortem: pm.id}) AS incidents
ORDER BY dec.updated_at DESC
LIMIT 5
