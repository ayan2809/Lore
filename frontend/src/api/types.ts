// TypeScript mirror of backend/lore/models.py (the contract).
// If you change a field in models.py, change it here in the same commit.
// Python `X | None` becomes `X | null`; Python defaults are always present in JSON.

// ---------------------------------------------------------------- identity

export type AccessLevel = 'public' | 'internal' | 'restricted' | 'confidential'
export type Employment = 'employee' | 'contractor'

export interface Viewer {
  id: string // "person:arjun"
  name: string
  employment: Employment
}

export interface Persona {
  id: string // "arjun"
  person_id: string // "person:arjun"
  name: string
  role: string
  can_see: string
  employment: Employment
}

// ---------------------------------------------------------------- tools

export type GraphMode = 'graph' | 'vector' // "vector" = Graph OFF baseline

export interface EdgeRef {
  source: string // node id property, e.g. "svc:checkout"
  target: string
  type: string // "DEPENDS_ON"
}

export interface ToolResult {
  tool: string
  reason: string
  data: Record<string, unknown>[]
  cypher: string
  ms: number
  node_ids: string[]
  edges: EdgeRef[]
  restricted_matches: number
  restricted_owner_hint: string | null
  error: string | null
}

// ---------------------------------------------------------------- reports and answers

export interface Claim {
  text: string
  citations: string[] // node ids returned by tools in this run
}

export interface PeopleToContact {
  page: string | null // owner on call, e.g. "person:rahul"
  consult: string[] // experts
  notify: string[] // authors
}

export type Severity = 'P1' | 'P2' | 'P3'

export interface Report {
  summary: string
  root_cause: string | null // node id, e.g. "pr:482"
  rejected_suspects: Claim[]
  severity: Severity | null
  claims: Claim[]
  evidence_path: string[]
  people: PeopleToContact
  confidence: number
  restricted_matches: number
  restricted_owner_hint: string | null
  dropped_claims: Claim[] // failed citation validation
}

export interface SourceRef {
  id: string
  source: string // "slack" | "github" | "jira" | "adr" | "wiki" | "runbook" | "incident" ...
  title: string | null
  updated_at: number | null // unix seconds
  access_level: AccessLevel | null
  conflict: boolean
}

/** GET /api/sources/{id}: a SourceRef plus its text. */
export interface SourceDetail extends SourceRef {
  text: string
}

export interface AskAnswer {
  question: string
  viewer_id: string
  mode: GraphMode
  claims: Claim[]
  sources: SourceRef[]
  refused: boolean
  restricted_matches: number
  restricted_owner_hint: string | null
  query_trace_id: string | null
  ms: number
}

// ---------------------------------------------------------------- actions (human in the loop)

export type ActionKind = 'slack_post' | 'github_issue' | 'rollback'
export type ActionStatus = 'proposed' | 'approved' | 'rejected' | 'blocked' | 'sent' | 'failed'

export interface Action {
  id: string // "action:<uuid>"
  investigation_id: string
  kind: ActionKind
  target: string // "#incidents" or "owner/repo"
  title: string | null
  text: string
  cited_ids: string[]
  status: ActionStatus
  blocked_reason: string | null
  result_url: string | null
  simulated: boolean
}

// ---------------------------------------------------------------- graph view for the UI

export interface GraphNode {
  id: string
  label: string // "Service", "Person", "PR", "Deploy", ...
  name: string
  access_level: AccessLevel | null
  props: Record<string, unknown>
}

export interface GraphView {
  nodes: GraphNode[]
  links: EdgeRef[]
}

export interface RunSummary {
  investigation_id: string
  steps: number
  model_calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
  total_ms: number
  time_to_root_cause_ms: number | null
  replay: boolean
}

// ---------------------------------------------------------------- streaming events
// The Python StepEvent has `payload: dict`. Here it is a union keyed on `type`,
// so TypeScript knows the payload shape after `switch (event.type)`.
// Payload shapes come from the SSE table in docs/PROJECT_CONTEXT.md section 6.

export type EventType = StepEvent['type']

export interface InvestigationStartedPayload {
  alert_id: string
  viewer_id: string
  mode: GraphMode
  replay: boolean
}
export interface AgentStartedPayload {
  agent: string
  goal: string
}
export interface AgentFinishedPayload {
  agent: string
  confidence?: number
  findings: number
}
export interface ToolCallPayload {
  tool: string
  reason: string
  args: Record<string, unknown>
}
export interface ToolResultPayload {
  tool: string
  reason: string
  cypher: string
  ms: number
  node_ids: string[]
  edges: EdgeRef[]
  restricted_matches: number
  restricted_owner_hint?: string | null // not in the contract table yet (see report)
  row_count: number
  error: string | null
}
export interface FindingPayload {
  text: string
  citations: string[]
  confidence: number
}
export interface PolicyBlockedPayload {
  action_id?: string
  reason: string
}
export interface ErrorPayload {
  message: string
  recoverable: boolean
}

interface EventBase {
  investigation_id: string
  seq: number
  ts: number // unix seconds
  agent: string | null // "triage" | "historian" | "investigator" | "responder"
}

export type StepEvent = EventBase &
  (
    | { type: 'investigation_started'; payload: InvestigationStartedPayload }
    | { type: 'agent_started'; payload: AgentStartedPayload }
    | { type: 'tool_call'; payload: ToolCallPayload }
    | { type: 'tool_result'; payload: ToolResultPayload }
    | { type: 'finding'; payload: FindingPayload }
    | { type: 'agent_finished'; payload: AgentFinishedPayload }
    | { type: 'report'; payload: Report }
    | { type: 'action_proposed'; payload: Action }
    | { type: 'policy_blocked'; payload: PolicyBlockedPayload }
    | { type: 'error'; payload: ErrorPayload }
    | { type: 'done'; payload: RunSummary }
  )

/** Every SSE event name, used to register one listener per type. */
export const EVENT_TYPES: EventType[] = [
  'investigation_started',
  'agent_started',
  'tool_call',
  'tool_result',
  'finding',
  'agent_finished',
  'report',
  'action_proposed',
  'policy_blocked',
  'error',
  'done',
]

// ---------------------------------------------------------------- HTTP request / response shapes

export interface Health {
  status: string
  falkordb: boolean
  gemini: boolean
  replay: boolean
}

export interface AlertItem {
  id: string // e.g. "alert:A-3001"
  name: string
  symptom: string
  service: string
  started_at: number // unix seconds
}

export interface GraphQuery {
  center?: string
  hops?: number
  limit?: number
}

export interface StartInvestigationRequest {
  alert_id: string
  mode: GraphMode
  replay?: boolean
}

/** GET /api/investigations/{id}: the final state, used to reconcile after `done`. */
export interface InvestigationSnapshot {
  report: Report | null
  summary: RunSummary
  actions: Action[]
}

export interface FeedbackRequest {
  confirmed: boolean
  note?: string
}

// ---------------------------------------------------------------- the API surface
// client.ts implements this against FastAPI; mock.ts implements it with fixtures.

export interface Api {
  health(): Promise<Health>
  personas(): Promise<Persona[]>
  getSession(): Promise<{ persona: Persona }>
  setSession(persona: string): Promise<{ persona: Persona }>
  alerts(): Promise<AlertItem[]>
  graph(query?: GraphQuery): Promise<GraphView>
  /** `replay_reason: 'daily_live_limit'` = today's live runs are used up, so a recording plays. */
  startInvestigation(
    req: StartInvestigationRequest,
  ): Promise<{ investigation_id: string; replay?: boolean; replay_reason?: string | null }>
  /** Returns an unsubscribe function. `onClose` fires after `done` or on a fatal stream error. */
  subscribeToInvestigation(
    id: string,
    onEvent: (event: StepEvent) => void,
    onClose?: (error?: Error) => void,
  ): () => void
  getInvestigation(id: string): Promise<InvestigationSnapshot>
  sendFeedback(id: string, body: FeedbackRequest): Promise<{ playbook_id?: string }>
  ask(body: { question: string; mode: GraphMode }): Promise<AskAnswer>
  editAction(id: string, text: string): Promise<Action>
  approveAction(id: string): Promise<Action>
  rejectAction(id: string): Promise<Action>
  getSource(id: string): Promise<SourceDetail>
}
