// memory_read_investigation: input for a playbook: the investigation's symptom, root cause
// and the tools it called, in order.
MATCH (inv:Investigation {id: $investigation_id})
OPTIONAL MATCH (s:Step)-[:PART_OF]->(inv)
WITH inv, s ORDER BY s.seq
RETURN inv.symptom AS symptom, inv.root_cause AS root_cause, collect(s.tool) AS tools,
       // the tools whose results contained the root cause, in order (FIX_LOG F-10)
       [x IN collect({tool: s.tool, hit: inv.root_cause IN s.node_ids}) WHERE x.hit | x.tool]
         AS key_tools
