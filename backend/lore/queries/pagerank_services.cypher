// pagerank_services: which services does the rest of the company lean on the most?
//
// PageRank is a graph algorithm built into FalkorDB. Run over DEPENDS_ON arrows it gives a high
// score to services that many (important) services depend on, such as auth or feature-flags.
// Not content, so there is no viewer filter.
//
// Params: $limit
CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
RETURN node.id AS id, node.name AS name, node.tier AS tier, score
ORDER BY score DESC
LIMIT $limit
