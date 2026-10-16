// memory_start_investigation: open a new investigation.
// The Investigation node is the agents' shared notebook ("blackboard"): every Step and
// Finding of this run hangs off it, so a run survives a restart.
// The second MATCH links it to its alert; if the alert is missing, the node is still created.
MERGE (inv:Investigation {id: $id})
SET inv.alert_id = $alert_id,
    inv.symptom = $symptom,
    inv.viewer = $viewer_id,
    inv.mode = $mode,
    inv.started_at = $started_at,
    inv.status = 'running'
WITH inv
MATCH (a:Alert {id: $alert_id})
MERGE (inv)-[:INVESTIGATES]->(a)
