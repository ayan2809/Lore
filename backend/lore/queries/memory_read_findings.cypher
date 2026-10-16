// memory_read_findings: everything earlier agents found in this investigation, oldest first.
MATCH (f:Finding)-[:PART_OF]->(:Investigation {id: $investigation_id})
RETURN f.agent AS agent, f.text AS text, f.citations AS citations, f.confidence AS confidence
ORDER BY f.ts, f.id
