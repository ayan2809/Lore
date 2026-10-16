// ask_supersedes: which of the retrieved sources replace which?
// Returns (newer, older) pairs for (newer)-[:SUPERSEDES]->(older) where BOTH ids are in $ids.
// $ids are sources this viewer was already allowed to retrieve, so no extra viewer filter is
// needed: this query only reveals a link between two things the viewer can already see.
// Example: adr:011 SUPERSEDES wiki:pricing-cache ("60s TTL is fine" is out of date).
MATCH (newer)-[:SUPERSEDES]->(older)
WHERE newer.id IN $ids AND older.id IN $ids
RETURN newer.id AS newer, older.id AS older
