// memory_expertise_open: semantic memory, step 2 of 2.
// Start the new EXPERT_IN fact with its score. valid_to is left unset (null) until a later
// update closes it.
MATCH (p:Person {id: $person_id}), (s:Service {id: $service_id})
CREATE (p)-[:EXPERT_IN {score: $score, valid_from: $now}]->(s)
