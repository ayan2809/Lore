// memory_current_expertise: the currently valid EXPERT_IN score for one person and service.
MATCH (:Person {id: $person_id})-[r:EXPERT_IN]->(:Service {id: $service_id})
WHERE r.valid_to IS NULL
RETURN r.score AS score
