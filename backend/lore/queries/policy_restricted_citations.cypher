// policy_restricted_citations: which cited sources are restricted or confidential?
//
// A GitHub issue lands in a repository that people outside the restricted teams can read (the
// demo repo is public), so it may never cite a restricted or confidential source, the same rule
// as an open Slack channel (FIX_LOG F-09). Returns one row per offending id; none = allowed.
//
// Params: $cited_ids
MATCH (n)
WHERE n.id IN $cited_ids AND n.access_level IN ['restricted', 'confidential']
RETURN n.id AS source_id, n.access_level AS access_level
