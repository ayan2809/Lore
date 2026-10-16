// action_upsert.cypher
// Purpose: save (or update) one human-in-the-loop Action and link it to its Investigation.
// Used by: lore/actions.py (the only code that writes Action nodes).
// Params: $id, $investigation_id, $kind, $target, $title, $text, $cited_ids, $status,
//         $blocked_reason, $result_url, $simulated
// Note: the SET runs before the MATCH, so the Action is saved even if the Investigation node
// does not exist (for example when the investigation is a replay).
MERGE (a:Action {id: $id})
SET a.investigation_id = $investigation_id,
    a.kind = $kind,
    a.target = $target,
    a.title = $title,
    a.text = $text,
    a.cited_ids = $cited_ids,
    a.status = $status,
    a.blocked_reason = $blocked_reason,
    a.result_url = $result_url,
    a.simulated = $simulated
WITH a
MATCH (i:Investigation {id: $investigation_id})
MERGE (i)-[:PROPOSED]->(a)
RETURN a.id AS id
