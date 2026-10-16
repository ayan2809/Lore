// alert_context: one alert, the service it fired on and when it started.
//
// This is where an investigation starts: the Supervisor reads `started_at` to decide what
// "recent" means for recent_changes, and `service` is the failing service for blast_radius.
//
// Params: $alert (e.g. 'alert:A-3001')
MATCH (a:Alert {id: $alert})-[:FIRED_ON]->(s:Service)
RETURN a.id AS id,
       a.name AS name,
       a.symptom AS symptom,
       a.started_at AS started_at,
       s.id AS service,
       s.name AS service_name,
       s.tier AS tier
LIMIT 1
