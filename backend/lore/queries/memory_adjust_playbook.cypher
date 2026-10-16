// memory_adjust_playbook: feedback. A confirmed result adds 1 to success_count, a rejected
// one takes 1.
// Good playbooks rise in memory_find_playbooks; bad ones sink and are eventually skipped.
MATCH (p:Playbook {id: $id})
SET p.success_count = coalesce(p.success_count, 0) + $delta
RETURN p.success_count AS success_count
