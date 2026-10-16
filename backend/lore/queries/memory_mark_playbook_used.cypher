// memory_mark_playbook_used: remember which playbook guided this investigation, so feedback on the
// result can raise or lower that playbook's success_count.
MATCH (inv:Investigation {id: $investigation_id}), (p:Playbook {id: $playbook_id})
MERGE (inv)-[:USED_PLAYBOOK]->(p)
