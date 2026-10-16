// memory_query_trace: audit trail for "Ask the brain", one Query node per question (plan 12).
// It records ids only, never source text, so the trace itself cannot leak content.
// filtered_count = matching sources the viewer was NOT allowed to see (count only).
CREATE (q:Query {
  id: $id, question: $question, viewer: $viewer_id, mode: $mode,
  retrieved_ids: $retrieved_ids, filtered_count: $filtered_count,
  reranked_ids: $reranked_ids, cited_ids: $cited_ids, refused: $refused,
  ms: $ms, tokens_in: $tokens_in, tokens_out: $tokens_out, cost_usd: $cost_usd, ts: $ts
})
RETURN q.id AS id
