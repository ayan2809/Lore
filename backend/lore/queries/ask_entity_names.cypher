// ask_entity_names: names Ask can recognise in a question (services, people, teams).
//
// Only names and ids of org-chart nodes, which every viewer may see; no content.
MATCH (n)
WHERE labels(n)[0] IN ['Service', 'Person', 'Team']
RETURN n.id AS id, labels(n)[0] AS label, n.name AS name
