// recent_changes: what changed lately in this service or in anything it depends on?
//
// 1. Take the failing service and everything it depends on, up to 3 hops downstream (hops = 0
//    is the service itself).
// 2. Find deploys to those services between $since and $until (the alert time), the PRs inside
//    each deploy (INCLUDES), who wrote them (AUTHORED) and which code modules they changed
//    (MODIFIES). The module list is what separates a real suspect (a config change in
//    pricing) from a red herring (a button-copy change in checkout).
//
// Permissions: PRs carry an access_level, so the viewer filter is applied to them (a contractor
// gets nothing). A Deploy carries no content, but we treat it as "internal" so contractors
// do not get deploy metadata either.
//
// Params: $service, $since, $until, $viewer, $open_levels
MATCH (viewer:Person {id: $viewer})
MATCH p = (:Service {id: $service})-[:DEPENDS_ON*0..3]->(dep:Service)
WITH viewer, dep, min(length(p)) AS hops
MATCH (dep)<-[:DEPLOYED_TO]-(d:Deploy)-[:INCLUDES]->(pr:PR)
WHERE d.at > $since AND d.at <= $until
  AND coalesce(d.access_level, 'internal') IN $open_levels
  AND (pr.access_level IN $open_levels
       OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(pr))
OPTIONAL MATCH (pr)<-[:AUTHORED]-(a:Person)
OPTIONAL MATCH (pr)-[:MODIFIES]->(m:CodeModule)
RETURN dep.id AS service_id,
       dep.name AS service,
       hops,
       d.id AS deploy_id,
       d.at AS deployed_at,
       pr.id AS pr_id,
       pr.number AS pr_number,
       pr.title AS pr_title,
       pr.access_level AS access_level,
       a.id AS author_id,
       a.name AS author,
       collect(DISTINCT m.id) AS modules
ORDER BY d.at DESC
