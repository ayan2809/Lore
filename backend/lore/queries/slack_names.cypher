// slack_names: human names for the ids in an approved report, so Slack says "PR #482 by Priya
// Nair" instead of "pr:482 ... person:priya" (HUMAN_REVIEW R-36).
//
// Only names, titles and numbers, for ids that the report already cites. The report's ids all came
// from permission-filtered tools, and the post-audience check runs before anything is sent.
//
// Params: $ids
MATCH (n)
WHERE n.id IN $ids
RETURN n.id AS id,
       labels(n)[0] AS label,
       n.name AS name,
       n.title AS title,
       n.number AS number,
       n.symptom AS symptom
