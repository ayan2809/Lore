// blast_radius: which services are hurt if this service breaks?
//
// Follow DEPENDS_ON arrows BACKWARDS (from the failing service to the services that depend on
// it), up to 4 hops. The failing service itself comes back with hops = 0. For each service we
// keep the shortest chain (`via`, a list of service ids from the failing service outwards),
// which the UI uses to light up the edges.
//
// Services and their dependencies are org-chart data, not content, so there is no viewer filter.
//
// Params: $service (e.g. 'svc:checkout')
MATCH p = (s:Service {id: $service})<-[:DEPENDS_ON*0..4]-(up:Service)
WITH up, length(p) AS hops, [n IN nodes(p) | n.id] AS via
ORDER BY hops
WITH up, min(hops) AS hops, collect(via)[0] AS via
RETURN up.id AS id, up.name AS name, up.tier AS tier, hops, via
ORDER BY hops, tier, id
