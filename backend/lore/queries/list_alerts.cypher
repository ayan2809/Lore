// list_alerts: the alerts the demo can investigate (A-3001, A-3002) and the service each fired on.
//
// Alerts are operational data, not company content, so there is no viewer filter here.
//
// No params.
MATCH (a:Alert)-[:FIRED_ON]->(s:Service)
RETURN a.id AS id,
       a.name AS name,
       a.symptom AS symptom,
       s.id AS service,
       a.started_at AS started_at
ORDER BY a.started_at
