// who_knows: who really knows this service, and who owns it on the org chart?
//
// Two kinds of answer come back, told apart by the columns on_owner_team and is_lead:
//   - the OWNER side (page these people): members of the team that OWNS the service, and the
//     team lead (the member with the eng-manager role);
//   - the EXPERT side (consult these people): anyone with a track record on the service's code.
//
// Expertise score = code_score + incident_score
//   code_score     3 points per PR they AUTHORED in the service's repo, 1 per PR they REVIEWED
//   incident_score 5 points per past incident on this service that they were RESOLVED_BY
//   authored       how many of those PRs they wrote (used to spot a bus factor of 1)
//
// "Current team" uses MEMBER_OF only. A person who moved away has WAS_MEMBER_OF instead, so
// they are never reported as owning the service (this is why Marco is a consult, not a page).
//
// Permissions: PRs and incidents are content, so only the ones the viewer may see are counted.
// Python sorts by score and keeps the top few (ORDER BY/LIMIT are not used before a UNION).
// The second half of the UNION adds the owning team's lead from the org chart even if they have
// no visible PRs, so there is always someone to page.
//
// Params: $service, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH (svc:Service {id: $service})-[:BUILT_FROM]->(:Repo)<-[:IN_REPO]-(pr:PR)<-[r:AUTHORED|REVIEWED]-(p:Person)
WHERE pr.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(pr)
WITH viewer, svc, p,
     sum(CASE type(r) WHEN 'AUTHORED' THEN 3 ELSE 1 END) AS code_score,
     sum(CASE type(r) WHEN 'AUTHORED' THEN 1 ELSE 0 END) AS authored
OPTIONAL MATCH (i:Incident)-[:RESOLVED_BY]->(p)
WHERE (i)-[:AFFECTED]->(svc)
  AND (i.access_level IN $open_levels
       OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(i))
WITH svc, p, code_score, authored, 5 * count(DISTINCT i) AS incident_score
OPTIONAL MATCH (p)-[:MEMBER_OF]->(team:Team)
OPTIONAL MATCH (owner:Team)-[:OWNS]->(svc)
OPTIONAL MATCH (p)-[:HAS_ROLE]->(lead_role:Role {id: 'role:eng-manager'})
RETURN p.id AS id,
       p.name AS name,
       code_score,
       incident_score,
       authored,
       code_score + incident_score AS score,
       team.id AS current_team,
       owner.id AS owner_team,
       team.id = owner.id AS on_owner_team,
       lead_role IS NOT NULL AND team.id = owner.id AS is_lead
UNION
MATCH (owner:Team)-[:OWNS]->(:Service {id: $service})
MATCH (lead:Person)-[:MEMBER_OF]->(owner)
WHERE (lead)-[:HAS_ROLE]->(:Role {id: 'role:eng-manager'})
RETURN lead.id AS id,
       lead.name AS name,
       0 AS code_score,
       0 AS incident_score,
       0 AS authored,
       0 AS score,
       owner.id AS current_team,
       owner.id AS owner_team,
       true AS on_owner_team,
       true AS is_lead
