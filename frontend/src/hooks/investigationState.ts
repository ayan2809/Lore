// Pure state logic for one investigation: no React, no network.
// `reduce(state, message)` turns the SSE StepEvents into what the panels render.

import type { Action, EdgeRef, GraphMode, InvestigationSnapshot, Report, RunSummary, StepEvent } from '../api/types'

// Ids that tools return but that are not graph nodes, so the canvas must not draw or zoom to them.
const NON_GRAPH_PREFIXES = ['action:', 'inv:', 'step:', 'finding:', 'query:']

// ---------------------------------------------------------------- trail items

/** One row in the reasoning trail. `seq` is the SSE sequence number, used as React key. */
export type TrailItem =
  | { kind: 'agent'; seq: number; agent: string; goal: string; done: boolean; confidence?: number; findings?: number }
  | {
      kind: 'tool'
      seq: number
      agent: string | null
      tool: string
      reason: string
      args: Record<string, unknown>
      status: 'running' | 'done' | 'error'
      cypher: string
      ms: number
      rowCount: number
      nodeIds: string[]
      edges: EdgeRef[]
      restrictedMatches: number
      error: string | null
    }
  | { kind: 'finding'; seq: number; agent: string | null; text: string; citations: string[]; confidence: number }
  | { kind: 'notice'; seq: number; level: 'error' | 'blocked'; message: string }

export type ToolItem = Extract<TrailItem, { kind: 'tool' }>

export interface InvestigationState {
  status: 'idle' | 'starting' | 'running' | 'done' | 'failed'
  investigationId: string | null
  alertId: string | null
  mode: GraphMode
  replay: boolean
  trail: TrailItem[]
  selectedSeq: number | null // a trail step the user clicked (null = follow the latest)
  report: Report | null
  actions: Action[]
  summary: RunSummary | null
  error: string | null
  lastSeq: number // highest seq applied; used to drop duplicates after an SSE reconnect
}

export const initialState: InvestigationState = {
  status: 'idle',
  investigationId: null,
  alertId: null,
  mode: 'graph',
  replay: false,
  trail: [],
  selectedSeq: null,
  report: null,
  actions: [],
  summary: null,
  error: null,
  lastSeq: -1,
}

// ---------------------------------------------------------------- reducer

export type Message =
  | { t: 'starting'; alertId: string; mode: GraphMode; replay: boolean }
  | { t: 'started'; investigationId: string }
  | { t: 'event'; event: StepEvent }
  | { t: 'select'; seq: number | null }
  | { t: 'action'; action: Action }
  | { t: 'snapshot'; snapshot: InvestigationSnapshot }
  | { t: 'failed'; message: string }
  | { t: 'clear' }

const upsertAction = (list: Action[], action: Action) =>
  list.some((a) => a.id === action.id) ? list.map((a) => (a.id === action.id ? action : a)) : [...list, action]

export function reduce(state: InvestigationState, msg: Message): InvestigationState {
  switch (msg.t) {
    case 'clear':
      return initialState
    case 'starting':
      return { ...initialState, status: 'starting', alertId: msg.alertId, mode: msg.mode, replay: msg.replay }
    case 'started':
      return { ...state, status: 'running', investigationId: msg.investigationId }
    case 'select':
      return { ...state, selectedSeq: msg.seq }
    case 'action':
      return { ...state, actions: upsertAction(state.actions, msg.action) }
    case 'failed':
      return { ...state, status: 'failed', error: msg.message }
    case 'snapshot':
      // Final truth from GET /investigations/{id}; fills anything the stream missed.
      return {
        ...state,
        report: msg.snapshot.report ?? state.report,
        summary: msg.snapshot.summary ?? state.summary,
        actions: msg.snapshot.actions.length ? msg.snapshot.actions : state.actions,
      }
    case 'event':
      return applyEvent(state, msg.event)
  }
}

function applyEvent(state: InvestigationState, e: StepEvent): InvestigationState {
  if (e.seq <= state.lastSeq) return state // duplicate after reconnect
  const next = { ...state, lastSeq: e.seq }

  switch (e.type) {
    case 'investigation_started':
      return { ...next, replay: e.payload.replay, mode: e.payload.mode }

    case 'agent_started':
      return {
        ...next,
        trail: [...next.trail, { kind: 'agent', seq: e.seq, agent: e.payload.agent, goal: e.payload.goal, done: false }],
      }

    case 'agent_finished':
      return {
        ...next,
        trail: next.trail.map((t) =>
          t.kind === 'agent' && t.agent === e.payload.agent && !t.done
            ? { ...t, done: true, confidence: e.payload.confidence, findings: e.payload.findings }
            : t,
        ),
      }

    case 'tool_call':
      return {
        ...next,
        trail: [
          ...next.trail,
          {
            kind: 'tool',
            seq: e.seq,
            agent: e.agent,
            tool: e.payload.tool,
            reason: e.payload.reason,
            args: e.payload.args,
            status: 'running',
            cypher: '',
            ms: 0,
            rowCount: 0,
            nodeIds: [],
            edges: [],
            restrictedMatches: 0,
            error: null,
          },
        ],
      }

    case 'tool_result': {
      const p = e.payload
      const done = {
        status: p.error ? ('error' as const) : ('done' as const),
        cypher: p.cypher,
        ms: p.ms,
        rowCount: p.row_count,
        // Only graph nodes can be drawn; ids like action:… are not in the graph.
        nodeIds: p.node_ids.filter((id) => !NON_GRAPH_PREFIXES.some((x) => id.startsWith(x))),
        edges: p.edges,
        restrictedMatches: p.restricted_matches,
        error: p.error,
      }
      // Fill in the most recent running call to the same tool.
      let idx = -1
      for (let i = next.trail.length - 1; i >= 0; i--) {
        const t = next.trail[i]
        if (t.kind === 'tool' && t.status === 'running' && t.tool === p.tool) {
          idx = i
          break
        }
      }
      if (idx === -1) {
        // No matching tool_call (e.g. a replay that skipped it): add a finished row.
        const row: ToolItem = {
          kind: 'tool', seq: e.seq, agent: e.agent, tool: p.tool, reason: p.reason, args: {}, ...done,
        }
        return { ...next, trail: [...next.trail, row] }
      }
      return {
        ...next,
        trail: next.trail.map((t, i) => (i === idx && t.kind === 'tool' ? { ...t, reason: p.reason || t.reason, ...done } : t)),
      }
    }

    case 'finding':
      return {
        ...next,
        trail: [
          ...next.trail,
          { kind: 'finding', seq: e.seq, agent: e.agent, text: e.payload.text, citations: e.payload.citations, confidence: e.payload.confidence },
        ],
      }

    case 'report':
      return { ...next, report: e.payload }

    case 'action_proposed':
      return { ...next, actions: upsertAction(next.actions, e.payload) }

    case 'policy_blocked': {
      const { action_id, reason } = e.payload
      return {
        ...next,
        actions: next.actions.map((a) =>
          a.id === action_id ? { ...a, status: 'blocked', blocked_reason: reason } : a,
        ),
        trail: [...next.trail, { kind: 'notice', seq: e.seq, level: 'blocked', message: reason }],
      }
    }

    case 'error':
      return {
        ...next,
        // A non-recoverable error ends the run; recoverable ones are only shown in the trail.
        status: e.payload.recoverable ? next.status : 'failed',
        error: e.payload.recoverable ? next.error : e.payload.message,
        trail: [...next.trail, { kind: 'notice', seq: e.seq, level: 'error', message: e.payload.message }],
      }

    case 'done':
      return { ...next, status: next.status === 'failed' ? 'failed' : 'done', summary: e.payload }
  }
}

// ---------------------------------------------------------------- graph highlights

export interface Highlights {
  activeNodes: Set<string> // touched by the latest (or clicked) tool result: glows
  activeEdges: Set<string> // pairKey of the edges to animate
  seenNodes: Set<string> // touched earlier in the run: dim highlight
  seenEdges: Set<string>
  activeSeq: number | null
}

/** Order-independent key for an edge, so "a->b" and "b->a" match. */
export const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`)

export function computeHighlights(trail: TrailItem[], selectedSeq: number | null): Highlights {
  const tools = trail.filter((t): t is ToolItem => t.kind === 'tool' && t.nodeIds.length > 0)
  const active = selectedSeq !== null ? tools.find((t) => t.seq === selectedSeq) : tools[tools.length - 1]

  const h: Highlights = {
    activeNodes: new Set(),
    activeEdges: new Set(),
    seenNodes: new Set(),
    seenEdges: new Set(),
    activeSeq: active?.seq ?? null,
  }
  for (const t of tools) {
    const isActive = t === active
    for (const id of t.nodeIds) (isActive ? h.activeNodes : h.seenNodes).add(id)
    for (const e of t.edges) (isActive ? h.activeEdges : h.seenEdges).add(pairKey(e.source, e.target))
  }
  return h
}

/** Every node id and edge any tool touched. The canvas adds the ones the graph view lacks. */
export function discoveredFromTrail(trail: TrailItem[]): { nodeIds: string[]; edges: EdgeRef[] } {
  const nodeIds = new Set<string>()
  const edges = new Map<string, EdgeRef>()
  for (const t of trail) {
    if (t.kind !== 'tool') continue
    t.nodeIds.forEach((id) => nodeIds.add(id))
    t.edges.forEach((e) => edges.set(`${e.source}|${e.target}|${e.type}`, e))
  }
  return { nodeIds: [...nodeIds], edges: [...edges.values()] }
}
