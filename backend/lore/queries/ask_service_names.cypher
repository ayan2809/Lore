// ask_service_names: every service id and name, so code can spot a service named in a question
// ("Why is the pricing cache TTL 300s?" -> svc:pricing) and run graph-scoped search around it.
// Services are org-chart data, not content, so there is no viewer filter.
MATCH (s:Service)
RETURN s.id AS id, s.name AS name
