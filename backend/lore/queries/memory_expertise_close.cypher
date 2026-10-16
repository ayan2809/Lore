// memory_expertise_close: semantic memory, step 1 of 2.
// End the current EXPERT_IN fact by setting valid_to, instead of deleting it, so "who knew
// pricing in March?" can still be answered from history.
MATCH (:Person {id: $person_id})-[r:EXPERT_IN]->(:Service {id: $service_id})
WHERE r.valid_to IS NULL
SET r.valid_to = $now
