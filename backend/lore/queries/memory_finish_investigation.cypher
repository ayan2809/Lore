// memory_finish_investigation: close an investigation with its outcome.
MATCH (inv:Investigation {id: $id})
SET inv.status = $status,
    inv.root_cause = $root_cause,
    inv.finished_at = $finished_at
