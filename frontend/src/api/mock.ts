// Mock backend for `VITE_MOCK=1`. Implements the same `Api` as client.ts with fixtures
// and a scripted event stream, so the whole UI can be developed and demoed with no server.
//
// What it can show:
//   alert:A-3001  Story A (the 3 AM incident): red herring, root cause, restricted thread,
//                 a tool error + retry, a dropped claim, one action that gets blocked.
//   alert:A-3002  Story B (memory): the playbook is recalled, 4 tool steps instead of 11.
//   mode=vector   the Graph OFF baseline: weaker, no paths, wrong guess.
// Add `?speed=3` to the page URL to play the stream 3x faster.

import { ALERTS, E, PERSONAS, SOURCES, canSee, graphFor } from './mockData'
import type {
  Action, Api, AskAnswer, EdgeRef, GraphMode, Persona, Report, RunSummary, SourceDetail, SourceRef, StepEvent,
} from './types'

// ---------------------------------------------------------------- tiny helpers

const SPEED = Number(new URLSearchParams(window.location.search).get('speed')) || 1
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const latency = () => sleep(120)
const uid = () => Math.random().toString(36).slice(2, 10)

class MockHttpError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let persona: Persona = PERSONAS[0] // the "session"
const runs = new Map<string, Run>()
const actionIndex = new Map<string, Action>()

interface Run {
  id: string
  alertId: string
  mode: GraphMode
  replay: boolean
  persona: Persona
  report: Report | null
  summary: RunSummary | null
  actions: Action[]
}

// ---------------------------------------------------------------- scripted events

/** Omit that works on each member of a union (plain Omit would collapse the union). */
type DistributiveOmit<T, K extends keyof never> = T extends unknown ? Omit<T, K> : never
type Step = DistributiveOmit<StepEvent, 'investigation_id' | 'seq' | 'ts'> & { delay: number }

const agentStart = (agent: string, goal: string): Step => ({
  type: 'agent_started', agent, payload: { agent, goal }, delay: 600,
})
const agentEnd = (agent: string, confidence: number, findings: number): Step => ({
  type: 'agent_finished', agent, payload: { agent, confidence, findings }, delay: 500,
})
const finding = (agent: string, text: string, citations: string[], confidence = 0.85): Step => ({
  type: 'finding', agent, payload: { text, citations, confidence }, delay: 900,
})

interface ToolSpec {
  tool: string
  reason: string
  args: Record<string, unknown>
  cypher: string
  ms: number
  nodes: string[]
  edges: EdgeRef[]
  error?: string
}

/**
 * A tool_call followed by its tool_result. Nodes the viewer may not see are removed and only
 * COUNTED (restricted_matches), exactly like the real backend does inside Cypher.
 */
function toolSteps(agent: string, who: Persona, s: ToolSpec): Step[] {
  const shown = s.nodes.filter((id) => canSee(who.id, id))
  const hidden = s.nodes.length - shown.length
  const ok = new Set(shown)
  return [
    { type: 'tool_call', agent, payload: { tool: s.tool, reason: s.reason, args: s.args }, delay: 900 },
    {
      type: 'tool_result',
      agent,
      payload: {
        tool: s.tool,
        reason: s.reason,
        cypher: s.cypher,
        ms: s.ms,
        node_ids: shown,
        edges: s.edges.filter((e) => ok.has(e.source) && ok.has(e.target)),
        restricted_matches: hidden,
        restricted_owner_hint: hidden ? restrictedHint(who) : null,
        row_count: s.error ? 0 : shown.length,
        error: s.error ?? null,
      },
      delay: 700,
    },
  ]
}

const restrictedHint = (who: Persona) =>
  who.id === 'sam' ? 'your Kettle sponsor to request access' : 'ask the Pricing team (Rahul)'

// Permission predicate shown in the Cypher, like the real queries
const PERM = `WHERE src.access_level IN $open_levels
   OR (viewer)-[:MEMBER_OF|HAS_ROLE|IN_CHANNEL]->()<-[:VISIBLE_TO]-(src)`

// ---- Story A, graph ON

function storyA(who: Persona): { steps: Step[]; report: Report; actions: Action[] } {
  const steps: Step[] = [
    { type: 'investigation_started', agent: null, payload: { alert_id: 'alert:A-3001', viewer_id: who.person_id, mode: 'graph', replay: false }, delay: 300 },

    // ---- Triage
    agentStart('triage', 'Identify the alerting service and size the blast radius'),
    ...toolSteps('triage', who, {
      tool: 'find_entity', reason: 'Resolve the alert id to a node in the graph', args: { name: 'alert:A-3001' },
      cypher: 'MATCH (a:Alert {id: $id})-[r:FIRED_ON]->(s:Service)\nRETURN a.id, s.id, s.tier',
      ms: 1.8, nodes: ['alert:A-3001', 'svc:checkout'], edges: [E('alert:A-3001', 'svc:checkout', 'FIRED_ON')],
    }),
    ...toolSteps('triage', who, {
      tool: 'blast_radius', reason: 'What does checkout touch, and are tier-1 services in play? (input for severity)',
      args: { service: 'svc:checkout' },
      cypher: 'MATCH (s:Service {id: $service})-[:DEPENDS_ON*1..2]->(d:Service)\nRETURN d.id, d.tier ORDER BY d.tier',
      ms: 2.4,
      nodes: ['svc:checkout', 'svc:cart', 'svc:promo-engine', 'svc:payments-gateway', 'svc:orders', 'svc:auth'],
      edges: ['cart', 'promo-engine', 'payments-gateway', 'orders', 'auth'].map((d) => E('svc:checkout', `svc:${d}`, 'DEPENDS_ON')),
    }),
    finding('triage', 'Alert A-3001 fires on checkout, a tier-1 service, and 3 more tier-1 services are in its blast radius. Severity P1.', ['alert:A-3001', 'svc:checkout'], 0.9),
    agentEnd('triage', 0.9, 1),

    // ---- Historian
    agentStart('historian', 'Look for similar past incidents and decisions'),
    ...toolSteps('historian', who, {
      tool: 'similar_incidents', reason: 'Has "checkout latency" happened before?', args: { symptom: 'checkout p99 latency' },
      cypher: `CALL db.idx.vector.queryNodes('Chunk', 'embedding', 5, vecf32($qvec)) YIELD node AS c, score\nMATCH (c)-[:PART_OF]->(src:Incident), (viewer:Person {id: $viewer})\n${PERM}\nRETURN src.id, score`,
      ms: 6.9, nodes: ['inc:INC-0307', 'svc:pricing', 'svc:checkout'],
      edges: [E('inc:INC-0307', 'svc:pricing', 'AFFECTED'), E('inc:INC-0307', 'svc:checkout', 'AFFECTED')],
    }),
    ...toolSteps('historian', who, {
      tool: 'search_discussions', reason: 'Any decisions or chats about caching and latency in pricing?', args: { query: 'pricing cache TTL latency' },
      cypher: `CALL db.idx.vector.queryNodes('Chunk', 'embedding', 10, vecf32($qvec)) YIELD node AS c, score\nMATCH (c)-[:PART_OF]->(src), (viewer:Person {id: $viewer})\n${PERM}\nRETURN src.id, src.source, score`,
      ms: 8.1, nodes: ['adr:011', 'wiki:pricing-cache', 'thread:pricing-private-0142'],
      edges: [E('adr:011', 'wiki:pricing-cache', 'SUPERSEDES'), E('adr:011', 'thread:pricing-private-0142', 'DISCUSSED_IN')],
    }),
    ...toolSteps('historian', who, {
      tool: 'get_playbook', reason: 'Do we already have a playbook for this symptom?', args: { symptom: 'checkout p99 latency' },
      cypher: 'MATCH (p:Playbook) WHERE p.symptom CONTAINS $symptom RETURN p LIMIT 1',
      ms: 0.7, nodes: [], edges: [],
    }),
    finding('historian', 'INC-0307 (March 2026) was also a pricing overload after the pricing cache TTL was lowered, and ADR-011 says the TTL must stay at or above 300s.', ['inc:INC-0307', 'adr:011'], 0.8),
    agentEnd('historian', 0.8, 1),

    // ---- Investigator
    agentStart('investigator', 'Find the change that caused it and rule out red herrings'),
    ...toolSteps('investigator', who, {
      tool: 'recent_changes', reason: 'Checkout was deployed 12 minutes before the alert, so check that first',
      args: { service: 'svc:checkout', hours: 2 },
      cypher: 'MATCH (d:Deploy)-[:DEPLOYED_TO]->(s:Service {id: $service})\nWHERE d.at > $now - $hours * 3600\nMATCH (d)-[:INCLUDES]->(pr:PR)-[:MODIFIES]->(m:CodeModule)\nRETURN d.id, pr.id, m.id',
      ms: 3.2, nodes: ['svc:checkout', 'deploy:990', 'pr:479', 'mod:checkout/i18n/en.json', 'person:leah'],
      edges: [
        E('deploy:990', 'svc:checkout', 'DEPLOYED_TO'), E('deploy:990', 'pr:479', 'INCLUDES'),
        E('pr:479', 'mod:checkout/i18n/en.json', 'MODIFIES'), E('person:leah', 'pr:479', 'AUTHORED'),
      ],
    }),
    finding('investigator', 'PR #479 (deploy 990) only edits checkout/i18n/en.json (button copy). It cannot slow checkout down, so it is rejected as a suspect.', ['pr:479', 'deploy:990'], 0.85),
    // A failed call on purpose, so the red error state is visible. Delete these two steps to remove it.
    ...toolSteps('investigator', who, {
      tool: 'recent_changes', reason: 'checkout depends on promo-engine, which depends on pricing: what changed in pricing in the last 24h?',
      args: { service: 'svc:pricing', hours: 24 },
      cypher: 'MATCH (d:Deploy)-[:DEPLOYED_TO]->(s:Service {id: $service})\nWHERE d.at > $now - $hours * 3600\nRETURN d.id',
      ms: 2000.4, nodes: [], edges: [], error: 'Query timed out after 2000 ms',
    }),
    ...toolSteps('investigator', who, {
      tool: 'recent_changes', reason: 'Retry with a narrower window (12h)',
      args: { service: 'svc:pricing', hours: 12 },
      cypher: 'MATCH (d:Deploy)-[:DEPLOYED_TO]->(s:Service {id: $service})\nWHERE d.at > $now - $hours * 3600\nMATCH (d)-[:INCLUDES]->(pr:PR)-[:MODIFIES]->(m:CodeModule)\nOPTIONAL MATCH (a:Person)-[:AUTHORED]->(pr)\nRETURN d.id, pr.id, m.id, a.id',
      ms: 3.6, nodes: ['svc:pricing', 'deploy:991', 'pr:482', 'mod:pricing/config.yaml', 'person:priya', 'person:wei', 'ticket:PRC-311'],
      edges: [
        E('deploy:991', 'svc:pricing', 'DEPLOYED_TO'), E('deploy:991', 'pr:482', 'INCLUDES'),
        E('pr:482', 'mod:pricing/config.yaml', 'MODIFIES'), E('person:priya', 'pr:482', 'AUTHORED'),
        E('person:wei', 'pr:482', 'REVIEWED'), E('pr:482', 'ticket:PRC-311', 'FIXES'),
      ],
    }),
    ...toolSteps('investigator', who, {
      tool: 'evidence_path', reason: 'Prove the path from the alert to PR #482', args: { alert_id: 'alert:A-3001', pr_number: 482 },
      cypher: 'MATCH (a:Alert {id: $alert_id}), (pr:PR {id: $pr_id})\nCALL algo.SPpaths({sourceNode: a, targetNode: pr, relTypes: [\'FIRED_ON\',\'DEPENDS_ON\',\'DEPLOYED_TO\',\'INCLUDES\']})\nYIELD path RETURN path',
      ms: 0.9, nodes: ['alert:A-3001', 'svc:checkout', 'svc:promo-engine', 'svc:pricing', 'deploy:991', 'pr:482'],
      edges: [
        E('alert:A-3001', 'svc:checkout', 'FIRED_ON'), E('svc:checkout', 'svc:promo-engine', 'DEPENDS_ON'),
        E('svc:promo-engine', 'svc:pricing', 'DEPENDS_ON'), E('deploy:991', 'svc:pricing', 'DEPLOYED_TO'),
        E('deploy:991', 'pr:482', 'INCLUDES'),
      ],
    }),
    ...toolSteps('investigator', who, {
      tool: 'trace_decision', reason: 'Is there a decision about this setting?', args: { entity: 'mod:pricing/config.yaml' },
      cypher: `MATCH (d:Decision)-[:DISCUSSED_IN|SUPERSEDES|RECORDED_IN*0..1]-(src), (viewer:Person {id: $viewer})\n${PERM}\nRETURN d.id, src.id`,
      ms: 4.4, nodes: ['adr:011', 'inc:INC-0307', 'wiki:pricing-cache', 'thread:pricing-private-0142'],
      edges: [
        E('adr:011', 'wiki:pricing-cache', 'SUPERSEDES'), E('inc:INC-0307', 'adr:011', 'RECORDED_IN'),
        E('adr:011', 'thread:pricing-private-0142', 'DISCUSSED_IN'),
      ],
    }),
    finding('investigator', 'Root cause: PR #482 lowered the pricing cache TTL from 300s to 5s (deploy 991, 90 min before the alert). That breaks ADR-011.', ['pr:482', 'deploy:991', 'adr:011'], 0.93),
    agentEnd('investigator', 0.93, 2),

    // ---- Responder
    agentStart('responder', 'Find who to contact and draft the incident post'),
    ...toolSteps('responder', who, {
      tool: 'who_knows', reason: 'Who owns pricing, who knows it best, who wrote the change?', args: { service: 'svc:pricing' },
      cypher: 'MATCH (s:Service {id: $service})\nOPTIONAL MATCH (t:Team)-[:OWNS]->(s), (p:Person)-[:MEMBER_OF]->(t)\nOPTIONAL MATCH (e:Person)-[x:EXPERT_IN]->(s)\nRETURN p.id, e.id, x.score ORDER BY x.score DESC',
      ms: 3.9, nodes: ['svc:pricing', 'team:pricing', 'person:rahul', 'person:marco', 'person:priya'],
      edges: [E('team:pricing', 'svc:pricing', 'OWNS'), E('person:rahul', 'team:pricing', 'MEMBER_OF'), E('person:marco', 'svc:pricing', 'EXPERT_IN'), E('person:priya', 'pr:482', 'AUTHORED')],
    }),
  ]

  // ---- report (claims the viewer may not see are removed and counted, like the real validator path)
  const claim = (text: string, citations: string[]) => ({ text, citations })
  const wanted = [
    claim('PR #482 changed the pricing cache TTL from 300s to 5s in pricing/config.yaml.', ['pr:482', 'mod:pricing/config.yaml']),
    claim('Deploy 991 shipped PR #482 to pricing at 01:30 IST, about 90 minutes before the alert.', ['deploy:991', 'pr:482']),
    claim('checkout depends on promo-engine, which depends on pricing, so a pricing overload shows up as checkout latency.', ['svc:checkout', 'svc:promo-engine', 'svc:pricing']),
    claim('ADR-011 says the pricing cache TTL must stay at or above 300 seconds.', ['adr:011']),
    claim('The same mistake caused INC-0307 in March 2026 (TTL lowered to 30s).', ['inc:INC-0307']),
    claim('The reason: the vendor price API is rate limited to 200 req/min, and a low TTL pushes pricing past it (discussed in #pricing-private).', ['thread:pricing-private-0142']),
  ]
  const claims = wanted.filter((c) => c.citations.every((id) => canSee(who.id, id)))
  const hidden = wanted.length - claims.length
  const rootVisible = canSee(who.id, 'pr:482')

  const report: Report = {
    summary: rootVisible
      ? 'Checkout p99 latency exceeded 3s because PR #482 cut the pricing cache TTL from 300s to 5s, which overloads pricing (checkout → promo-engine → pricing).'
      : 'Not enough visible evidence to name a root cause. Some matching sources are restricted for your account.',
    root_cause: rootVisible ? 'pr:482' : null,
    rejected_suspects: canSee(who.id, 'pr:479')
      ? [claim('PR #479 (deploy 990, 12 min before the alert) only changed button copy in checkout/i18n/en.json, so it cannot cause latency.', ['pr:479', 'deploy:990'])]
      : [],
    severity: 'P1',
    claims,
    evidence_path: rootVisible ? ['alert:A-3001', 'svc:checkout', 'svc:promo-engine', 'svc:pricing', 'deploy:991', 'pr:482'] : [],
    people: { page: 'person:rahul', consult: ['person:marco'], notify: ['person:priya'] },
    confidence: rootVisible ? 0.93 : 0.4,
    restricted_matches: hidden,
    restricted_owner_hint: hidden ? restrictedHint(who) : null,
    // A claim the model made without a valid citation: the validator drops it and the UI flags it.
    dropped_claims: rootVisible ? [claim('Rolling back will restore latency within 2 minutes.', [])] : [],
  }

  // ---- actions. Dana's Slack draft quotes the private thread, so approving it is blocked by policy.
  const quotesPrivate = canSee(who.id, 'thread:pricing-private-0142')
  const slackText = [
    ':rotating_light: P1: checkout p99 > 3s (alert A-3001)',
    'Root cause: PR #482 lowered the pricing cache TTL from 300s to 5s, overloading pricing. Checkout reaches pricing through promo-engine.',
    'Not the cause: PR #479 (button copy only).',
    'Rule broken: ADR-011, TTL must be >= 300s [adr:011]',
    ...(quotesPrivate ? ['Background (from #pricing-private): "vendor allows 200 req/min, a 30s TTL already sits at 190" [thread:pricing-private-0142]'] : []),
    'Page: Rahul (owner). Consult: Marco. Notify: Priya.',
    'Proposed fix: revert PR #482 (rollback below).',
  ].join('\n')

  const inv = '' // filled in when the run is created
  const actions: Action[] = [
    {
      id: '', investigation_id: inv, kind: 'slack_post', target: '#incidents', title: 'P1: checkout latency caused by PR #482',
      text: slackText, cited_ids: quotesPrivate ? ['pr:482', 'adr:011', 'thread:pricing-private-0142'] : ['pr:482', 'adr:011'],
      status: 'proposed', blocked_reason: null, result_url: null, simulated: false,
    },
    {
      id: '', investigation_id: inv, kind: 'github_issue', target: 'kettle/pricing', title: 'Restore pricing cache TTL to 300s (ADR-011)',
      text: 'PR #482 set cache_ttl_seconds to 5, which violates ADR-011 and overloaded pricing (see alert A-3001).\nAcceptance: TTL back to >= 300s; promo freshness handled another way (PRC-311).',
      cited_ids: ['pr:482', 'adr:011', 'ticket:PRC-311'], status: 'proposed', blocked_reason: null, result_url: null, simulated: false,
    },
    {
      id: '', investigation_id: inv, kind: 'rollback', target: 'deploy:991', title: 'Roll back deploy 991 (simulated)',
      text: 'Revert deploy 991 on pricing (includes PR #482). Simulated: nothing is changed in any real system.',
      cited_ids: ['deploy:991', 'pr:482'], status: 'proposed', blocked_reason: null, result_url: null, simulated: true,
    },
  ]
  const visibleActions = rootVisible ? actions : []

  steps.push(
    finding('responder', 'Page Rahul (owner of pricing), consult Marco (the expert, now on Data), notify Priya (wrote PR #482).', ['person:rahul', 'person:marco', 'person:priya'], 0.9),
    { type: 'report', agent: 'responder', payload: report, delay: 900 },
  )
  visibleActions.forEach((a, i) => {
    a.id = `action:mock-${i + 1}`
    steps.push({ type: 'action_proposed', agent: 'responder', payload: a, delay: 500 })
  })
  steps.push(agentEnd('responder', 0.9, 1))
  return { steps, report, actions: visibleActions }
}

// ---- Story B (memory): the playbook from Story A makes this 4 tool steps

function storyB(who: Persona): { steps: Step[]; report: Report; actions: Action[] } {
  const claim = (text: string, citations: string[]) => ({ text, citations })
  const steps: Step[] = [
    { type: 'investigation_started', agent: null, payload: { alert_id: 'alert:A-3002', viewer_id: who.person_id, mode: 'graph', replay: false }, delay: 300 },
    agentStart('triage', 'Identify the alerting service'),
    ...toolSteps('triage', who, {
      tool: 'find_entity', reason: 'Resolve the alert to a service', args: { name: 'alert:A-3002' },
      cypher: 'MATCH (a:Alert {id: $id})-[:FIRED_ON]->(s:Service) RETURN a.id, s.id, s.tier',
      ms: 1.5, nodes: ['alert:A-3002', 'svc:dispatch'], edges: [E('alert:A-3002', 'svc:dispatch', 'FIRED_ON')],
    }),
    agentEnd('triage', 0.9, 0),
    agentStart('historian', 'Check memory for a matching playbook'),
    ...toolSteps('historian', who, {
      tool: 'get_playbook', reason: 'Latency alert on a tier-1 service: have we solved this shape before?', args: { symptom: 'latency alert after config change' },
      cypher: 'MATCH (p:Playbook)-[:LEARNED_FROM]->(i:Investigation) WHERE p.symptom CONTAINS $symptom\nRETURN p.id, p.steps, p.hit_count ORDER BY p.hit_count DESC LIMIT 1',
      ms: 1.1, nodes: ['playbook:cfg-ttl-1'], edges: [],
    }),
    finding('historian', 'Playbook recalled (learned from A-3001): look at recent config/TTL changes in a downstream dependency, then match the deploy to a PR.', ['playbook:cfg-ttl-1'], 0.9),
    agentEnd('historian', 0.9, 1),
    agentStart('investigator', 'Follow the playbook: recent config changes downstream of dispatch'),
    ...toolSteps('investigator', who, {
      tool: 'recent_changes', reason: 'Playbook step 1: config change in a dependency of dispatch (eta-predictor)', args: { service: 'svc:eta-predictor', hours: 12 },
      cypher: 'MATCH (d:Deploy)-[:DEPLOYED_TO]->(s:Service {id: $service})\nMATCH (d)-[:INCLUDES]->(pr:PR)-[:MODIFIES]->(m:CodeModule)\nRETURN d.id, pr.id, m.id',
      ms: 3.0, nodes: ['svc:dispatch', 'svc:eta-predictor', 'deploy:1034', 'pr:517', 'person:tomas'],
      edges: [
        E('svc:dispatch', 'svc:eta-predictor', 'DEPENDS_ON'), E('deploy:1034', 'svc:eta-predictor', 'DEPLOYED_TO'),
        E('deploy:1034', 'pr:517', 'INCLUDES'), E('person:tomas', 'pr:517', 'AUTHORED'),
      ],
    }),
    finding('investigator', 'Root cause: PR #517 cut the eta-predictor model cache TTL to 10s (deploy 1034). The notifications deploy 1035 (typo fix) is unrelated.', ['pr:517', 'deploy:1034'], 0.92),
    agentEnd('investigator', 0.92, 1),
    agentStart('responder', 'Find who to contact'),
    ...toolSteps('responder', who, {
      tool: 'who_knows', reason: 'Owner and author of the change', args: { service: 'svc:eta-predictor' },
      cypher: 'MATCH (t:Team)-[:OWNS]->(s:Service {id: $service}), (p:Person)-[:MEMBER_OF]->(t) RETURN p.id',
      ms: 2.2, nodes: ['team:dispatch', 'person:kofi', 'person:tomas'],
      edges: [E('team:dispatch', 'svc:eta-predictor', 'OWNS'), E('person:kofi', 'team:dispatch', 'MEMBER_OF')],
    }),
  ]
  const report: Report = {
    summary: 'Dispatch assignment latency is caused by PR #517, which cut the eta-predictor model cache TTL to 10s. Solved in 4 tool steps using the playbook learned from A-3001.',
    root_cause: 'pr:517',
    rejected_suspects: [claim('Deploy 1035 (PR #518) only fixed a typo in a push notification template.', ['pr:518', 'deploy:1035'])],
    severity: 'P1',
    claims: [
      claim('PR #517 reduced the eta-predictor model cache TTL to 10s.', ['pr:517']),
      claim('Deploy 1034 shipped it to eta-predictor, which dispatch depends on.', ['deploy:1034', 'svc:eta-predictor', 'svc:dispatch']),
    ],
    evidence_path: ['alert:A-3002', 'svc:dispatch', 'svc:eta-predictor', 'deploy:1034', 'pr:517'],
    people: { page: 'person:kofi', consult: [], notify: ['person:tomas'] },
    confidence: 0.92, restricted_matches: 0, restricted_owner_hint: null, dropped_claims: [],
  }
  const actions: Action[] = [
    {
      id: 'action:mock-b1', investigation_id: '', kind: 'slack_post', target: '#incidents', title: 'P1: dispatch latency caused by PR #517',
      text: ':rotating_light: P1: dispatch assignment latency > 5s (A-3002)\nRoot cause: PR #517 cut the eta-predictor cache TTL to 10s [pr:517]\nPage: Kofi (owner). Notify: Tomás (author).',
      cited_ids: ['pr:517', 'deploy:1034'], status: 'proposed', blocked_reason: null, result_url: null, simulated: false,
    },
  ]
  steps.push(
    finding('responder', 'Page Kofi (dispatch owner), notify Tomás (author of PR #517).', ['person:kofi', 'person:tomas'], 0.9),
    { type: 'report', agent: 'responder', payload: report, delay: 900 },
    { type: 'action_proposed', agent: 'responder', payload: actions[0], delay: 500 },
    agentEnd('responder', 0.9, 1),
  )
  return { steps, report, actions }
}

// ---- Graph OFF baseline: text search only, no paths, so it guesses

function vectorBaseline(who: Persona): { steps: Step[]; report: Report; actions: Action[] } {
  const search = (agent: string, query: string, nodes: string[]) =>
    toolSteps(agent, who, {
      tool: 'search_discussions', reason: 'Vector search only (Graph OFF): find text similar to the alert', args: { query },
      cypher: `CALL db.idx.vector.queryNodes('Chunk', 'embedding', 10, vecf32($qvec)) YIELD node AS c, score\nMATCH (c)-[:PART_OF]->(src), (viewer:Person {id: $viewer})\n${PERM}\nRETURN src.id, score`,
      ms: 7.5, nodes, edges: [],
    })
  const report: Report = {
    summary: 'The most similar text points at the recent checkout deploy (PR #479). No dependency path was checked, so this is a guess.',
    root_cause: 'pr:479', rejected_suspects: [], severity: null,
    claims: [{ text: 'PR #479 was deployed to checkout 12 minutes before the alert.', citations: ['pr:479', 'deploy:990'] }],
    evidence_path: [], people: { page: null, consult: [], notify: [] },
    confidence: 0.35, restricted_matches: 0, restricted_owner_hint: null, dropped_claims: [],
  }
  const steps: Step[] = [
    { type: 'investigation_started', agent: null, payload: { alert_id: 'alert:A-3001', viewer_id: who.person_id, mode: 'vector', replay: false }, delay: 300 },
    agentStart('triage', 'Match the alert text to similar documents'),
    ...search('triage', 'checkout p99 latency > 3s', ['alert:A-3001', 'svc:checkout']),
    agentEnd('triage', 0.5, 0),
    agentStart('investigator', 'Find the likely cause from similar text'),
    ...search('investigator', 'checkout deploy before alert', ['pr:479', 'deploy:990']),
    finding('investigator', 'The best text match is the recent checkout deploy (PR #479).', ['pr:479', 'deploy:990'], 0.35),
    agentEnd('investigator', 0.35, 1),
    { type: 'report', agent: 'investigator', payload: report, delay: 900 },
  ]
  return { steps, report, actions: [] }
}

function scriptFor(run: Run) {
  const script =
    run.mode === 'vector' ? vectorBaseline(run.persona) : run.alertId.includes('3002') ? storyB(run.persona) : storyA(run.persona)
  // A finding that cites something this viewer cannot see would leak it, so the backend never emits it.
  script.steps = script.steps.filter(
    (s) => s.type !== 'finding' || s.payload.citations.every((id) => canSee(run.persona.id, id)),
  )
  return script
}

// ---------------------------------------------------------------- the Api implementation

function subscribeToInvestigation(
  id: string,
  onEvent: (e: StepEvent) => void,
  onClose?: (error?: Error) => void,
): () => void {
  const run = runs.get(id)
  if (!run) {
    setTimeout(() => onClose?.(new Error('Unknown investigation')), 0)
    return () => {}
  }
  const { steps, report, actions } = scriptFor(run)
  actions.forEach((a) => {
    a.investigation_id = id
    actionIndex.set(a.id, a)
  })

  let timer: ReturnType<typeof setTimeout> | undefined
  let cancelled = false
  let seq = 0
  const t0 = Date.now()
  let rootCauseMs: number | null = null
  const toolCalls = steps.filter((s) => s.type === 'tool_call').length
  const rootCause = report.root_cause

  const next = (i: number) => {
    if (cancelled) return
    if (i >= steps.length) return finish()
    const { delay, ...step } = steps[i]
    timer = setTimeout(() => {
      if (cancelled) return
      const event = { ...step, investigation_id: id, seq: seq++, ts: Date.now() / 1000 } as StepEvent
      if (event.type === 'finding' && rootCause && event.payload.citations.includes(rootCause) && rootCauseMs === null) {
        rootCauseMs = Date.now() - t0
      }
      if (event.type === 'action_proposed') event.payload = { ...event.payload } // never share the mutable object
      onEvent(event)
      next(i + 1)
    }, delay / SPEED)
  }

  const finish = () => {
    const summary: RunSummary = {
      investigation_id: id,
      steps: toolCalls,
      model_calls: run.mode === 'vector' ? 4 : 4 + toolCalls,
      tokens_in: 1400 * toolCalls + 2100,
      tokens_out: 160 * toolCalls + 700,
      cost_usd: 0.0021 * toolCalls + 0.003,
      total_ms: Date.now() - t0,
      time_to_root_cause_ms: rootCauseMs,
      replay: run.replay,
    }
    run.report = report
    run.summary = summary
    run.actions = actions
    onEvent({ type: 'done', investigation_id: id, seq: seq++, ts: Date.now() / 1000, agent: null, payload: summary })
    onClose?.()
  }

  next(0)
  return () => {
    cancelled = true
    clearTimeout(timer)
  }
}

// ---- actions

const copy = (a: Action): Action => ({ ...a, cited_ids: [...a.cited_ids] })
const getAction = (id: string) => {
  const a = actionIndex.get(id)
  if (!a) throw new MockHttpError(404, 'Unknown action')
  return a
}

const isRestricted = (id: string) => {
  const level = SOURCES[id]?.access_level
  return level === 'restricted' || level === 'confidential'
}

// ---- ask the brain

function answerQuestion(question: string, mode: GraphMode): AskAnswer {
  const base: AskAnswer = {
    question, viewer_id: persona.person_id, mode, claims: [], sources: [],
    refused: false, restricted_matches: 0, restricted_owner_hint: null, query_trace_id: `trace-${uid()}`, ms: 380,
  }
  const q = question.toLowerCase()
  const ref = (id: string, conflict = false): SourceRef => {
    const s = SOURCES[id]
    return { id, source: s?.source ?? 'graph', title: s?.title ?? id, updated_at: s?.updated_at ?? null, access_level: s?.access_level ?? null, conflict }
  }

  if (/salary|transfer|hr-private|password|api key/.test(q)) {
    // the request policy refuses before any query runs; like the backend, the reason is claims[0]
    return { ...base, refused: true, ms: 4, claims: [{ text: 'Questions about HR matters, credentials and personal data are blocked by policy.', citations: [] }] }
  }

  if (/ttl|cache/.test(q)) {
    if (mode === 'vector') {
      // Graph OFF: finds the stale wiki page by text similarity and has no idea it was superseded.
      return {
        ...base, ms: 910,
        claims: [{ text: 'The pricing cache TTL can be 60 seconds; lower values are fine.', citations: ['wiki:pricing-cache'] }],
        sources: [ref('wiki:pricing-cache')],
      }
    }
    const wanted = [
      { text: 'The pricing cache TTL is 300 seconds because ADR-011 requires at least 300s: the vendor price API is rate limited.', citations: ['adr:011'] },
      { text: 'Lowering it to 30s caused INC-0307 in March 2026 (pricing overload, checkout timeouts).', citations: ['inc:INC-0307'] },
      { text: 'An older wiki page says 60s is fine, but ADR-011 supersedes it, so ignore that page.', citations: ['wiki:pricing-cache', 'adr:011'] },
      { text: 'The vendor allows 200 requests/min, which is why the floor is 300s (discussion in #pricing-private).', citations: ['thread:pricing-private-0142'] },
    ]
    const claims = wanted.filter((c) => c.citations.every((id) => canSee(persona.id, id)))
    const hidden = wanted.length - claims.length
    const ids = ['adr:011', 'inc:INC-0307', 'wiki:pricing-cache', 'thread:pricing-private-0142'].filter((id) => canSee(persona.id, id))
    return {
      ...base, claims,
      sources: ids.map((id) => ref(id, id === 'wiki:pricing-cache')), // the wiki page conflicts with the ADR
      restricted_matches: hidden, restricted_owner_hint: hidden ? restrictedHint(persona) : null,
    }
  }

  if (/ledger|who knows/.test(q)) {
    return {
      ...base, ms: 420,
      claims: [
        { text: 'Ines Duarte (payments) is the only person who has authored PRs on the ledger service: bus factor 1.', citations: ['person:ines', 'svc:ledger'] },
        { text: 'Hana Sato, the payments lead, reviews the ledger PRs.', citations: ['person:hana'] },
      ],
      sources: [ref('person:ines'), ref('svc:ledger'), ref('person:hana')],
    }
  }

  return base // nothing found: claims is empty and refused is false
}

// ---------------------------------------------------------------- export

export const mockApi: Api = {
  health: async () => ({ status: 'ok', falkordb: true, gemini: true, replay: false }),
  personas: async () => PERSONAS.map((p) => ({ ...p })),

  getSession: async () => {
    await latency()
    return { persona: { ...persona } }
  },
  setSession: async (id) => {
    await latency()
    persona = PERSONAS.find((p) => p.id === id) ?? persona
    return { persona: { ...persona } }
  },

  alerts: async () => ALERTS.map((a) => ({ ...a })),
  graph: async () => {
    await sleep(250)
    return graphFor(persona.id)
  },

  startInvestigation: async ({ alert_id, mode, replay }) => {
    await latency()
    const id = `inv-${uid()}`
    runs.set(id, { id, alertId: alert_id, mode, replay: !!replay, persona, report: null, summary: null, actions: [] })
    return { investigation_id: id }
  },
  subscribeToInvestigation,
  getInvestigation: async (id) => {
    await latency()
    const run = runs.get(id)
    if (!run) throw new MockHttpError(404, 'Unknown investigation')
    const empty: RunSummary = { investigation_id: id, steps: 0, model_calls: 0, tokens_in: 0, tokens_out: 0, cost_usd: 0, total_ms: 0, time_to_root_cause_ms: null, replay: run.replay }
    return { report: run.report, summary: run.summary ?? empty, actions: run.actions.map(copy) }
  },
  sendFeedback: async (_id, body) => {
    await latency()
    return body.confirmed ? { playbook_id: 'playbook:cfg-ttl-1' } : {}
  },

  ask: async ({ question, mode }) => {
    await sleep(700)
    return answerQuestion(question, mode)
  },

  // Editing keeps a restricted citation only while the text still mentions it,
  // so deleting the quoted line from the post is what unblocks it.
  editAction: async (id, text) => {
    await latency()
    const a = getAction(id)
    a.text = text
    a.cited_ids = a.cited_ids.filter((c) => !isRestricted(c) || text.includes(c))
    if (a.status === 'blocked') {
      a.status = 'proposed'
      a.blocked_reason = null
    }
    return copy(a)
  },
  approveAction: async (id) => {
    await sleep(500)
    const a = getAction(id)
    const leaked = a.kind === 'slack_post' ? a.cited_ids.find(isRestricted) : undefined
    if (leaked) {
      a.status = 'blocked'
      a.blocked_reason = `Blocked: ${a.target} can be read by every employee, but ${leaked} is restricted to #pricing-private and the incident-commander role. Remove it from the post or choose a private channel.`
      return copy(a)
    }
    a.status = 'sent'
    a.blocked_reason = null
    if (!a.simulated) {
      a.result_url = a.kind === 'github_issue' ? 'https://github.com/kettle/pricing/issues/1' : 'https://kettle.example/slack/incidents/p1760393000'
    }
    return copy(a)
  },
  rejectAction: async (id) => {
    await latency()
    const a = getAction(id)
    a.status = 'rejected'
    return copy(a)
  },

  getSource: async (id) => {
    await latency()
    const s = SOURCES[id]
    if (s && !canSee(persona.id, id)) throw new MockHttpError(404, 'Not found') // same as the backend: 404 if not visible
    const detail: SourceDetail = s
      ? { id, conflict: id === 'wiki:pricing-cache', ...s }
      : {
          id, source: 'graph', title: id, updated_at: null, access_level: null, conflict: false,
          text: `${id} is a graph node, not a document. (Mock mode has text only for PRs, ADR-011, INC-0307, the wiki page, the runbook, the ticket and the private thread.)`,
        }
    return detail
  },
}
