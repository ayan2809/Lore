// post_audience_check: may this message be posted to this channel with these citations?
//
// Rule (plan section 6): everyone who can read the channel must be allowed to see every source
// the message cites. The query returns one row per violation; no rows means the post is fine.
//
// Branch 1: a current channel member (IN_CHANNEL; WAS_IN_CHANNEL does not count) who cannot see
//           a cited source. A reader may see a source if its level is open to them (contractors
//           only get 'public', identified by the contractor role or employment property) or if
//           they have a current path  reader -> team/role/channel <- VISIBLE_TO <- source.
// Branch 2: an open (non-private) channel can be read by every employee, not just its current
//           members, so restricted and confidential sources can never be cited there.
//
// Params: $channel, $cited_ids
MATCH (ch:Channel {id: $channel})<-[:IN_CHANNEL]-(reader:Person)
MATCH (src)
WHERE src.id IN $cited_ids AND src.access_level IS NOT NULL
OPTIONAL MATCH (reader)-[:HAS_ROLE]->(cr:Role {id: 'role:contractor'})
WITH reader, src, (cr IS NOT NULL OR reader.employment = 'contractor') AS is_contractor
// Pass-through WITH: FalkorDB 4.18 errors ("Type mismatch: expected Null but was Pointer") on a
// path pattern in a WHERE attached to a WITH that also computes a new value. See docs/STATE.md C-02.
WITH reader, src, is_contractor
WHERE NOT (src.access_level = 'public'
           OR (src.access_level = 'internal' AND NOT is_contractor)
           OR (reader)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src))
RETURN reader.id AS reader_id, reader.name AS reader_name, src.id AS source_id,
       'member cannot see source' AS reason
UNION
MATCH (ch:Channel {id: $channel})
MATCH (src)
WHERE src.id IN $cited_ids
  AND src.access_level IN ['restricted', 'confidential']
  AND ch.private = false
RETURN 'everyone' AS reader_id, 'all employees' AS reader_name, src.id AS source_id,
       'open channel, restricted source' AS reason
