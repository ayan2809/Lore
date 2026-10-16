// Fixtures for mock mode (VITE_MOCK=1). Ids and facts follow docs/story-bible.md.
// This file is only data; the scripted event stream lives in mock.ts.

import type { AccessLevel, AlertItem, EdgeRef, GraphNode, GraphView, Persona, SourceDetail } from './types'

const ts = (iso: string) => Math.floor(Date.parse(iso) / 1000)

// ---------------------------------------------------------------- personas (story bible section 4)

export const PERSONAS: Persona[] = [
  {
    id: 'arjun', person_id: 'person:arjun', name: 'Arjun Mehta', role: 'On-call engineer, Checkout',
    can_see: 'public + internal + Checkout and on-call channels', employment: 'employee',
  },
  {
    id: 'dana', person_id: 'person:dana', name: 'Dana Okafor', role: 'Incident commander + security',
    can_see: 'everything except HR', employment: 'employee',
  },
  {
    id: 'sam', person_id: 'person:sam', name: 'Sam Rivera', role: 'Contractor',
    can_see: 'public only', employment: 'contractor',
  },
  {
    id: 'marco', person_id: 'person:marco', name: 'Marco Bianchi', role: 'Data team (ex-Pricing)',
    can_see: 'internal; lost #pricing-private when he moved teams', employment: 'employee',
  },
]

export const ALERTS: AlertItem[] = [
  {
    id: 'alert:A-3001', name: 'A-3001', symptom: 'checkout p99 latency > 3s',
    service: 'svc:checkout', started_at: ts('2026-10-13T21:30:00Z'), // 03:00 IST on 14 Oct
  },
  {
    id: 'alert:A-3002', name: 'A-3002', symptom: 'dispatch assignment latency > 5s',
    service: 'svc:dispatch', started_at: ts('2026-10-20T21:40:00Z'), // 03:10 IST on 21 Oct
  },
]

// ---------------------------------------------------------------- who may see what (mock rule)

const OPEN: Record<string, AccessLevel[]> = {
  arjun: ['public', 'internal'],
  marco: ['public', 'internal'],
  sam: ['public'],
  dana: ['public', 'internal', 'restricted', 'confidential'],
}

/** Mirrors the backend rule closely enough for demos: sources have an access level, the rest is open. */
export function canSee(personaId: string, id: string): boolean {
  const level = SOURCES[id]?.access_level
  return !level || (OPEN[personaId] ?? OPEN.arjun).includes(level)
}

// ---------------------------------------------------------------- services (story bible section 6)

type Svc = [name: string, tier: number, owner: string, dependsOn: string[]]

const SERVICES: Svc[] = [
  ['api-gateway', 1, 'platform', ['auth']],
  ['auth', 1, 'platform', ['user-profile']],
  ['checkout', 1, 'checkout', ['cart', 'promo-engine', 'payments-gateway', 'orders', 'auth']],
  ['cart', 2, 'checkout', ['menu', 'inventory']],
  ['promo-engine', 2, 'checkout', ['pricing', 'feature-flags']],
  ['pricing', 1, 'pricing', ['menu', 'config-service', 'feature-flags']],
  ['surge-pricing', 2, 'pricing', ['pricing', 'rider-location']],
  ['menu', 2, 'pricing', ['restaurant-catalog']],
  ['restaurant-catalog', 3, 'data', []],
  ['inventory', 2, 'checkout', ['restaurant-catalog']],
  ['orders', 1, 'checkout', ['ledger', 'notifications']],
  ['payments-gateway', 1, 'payments', ['fraud-check', 'ledger']],
  ['ledger', 2, 'payments', []],
  ['fraud-check', 2, 'payments', ['user-profile']],
  ['refunds', 2, 'payments', ['ledger', 'payments-gateway']],
  ['invoices', 3, 'payments', ['ledger']],
  ['courier-payouts', 2, 'payments', ['ledger']],
  ['dispatch', 1, 'dispatch', ['eta-predictor', 'rider-location', 'orders']],
  ['eta-predictor', 2, 'dispatch', ['maps-proxy', 'feature-flags']],
  ['rider-location', 2, 'dispatch', ['maps-proxy']],
  ['maps-proxy', 3, 'dispatch', []],
  ['notifications', 2, 'platform', ['user-profile']],
  ['user-profile', 2, 'platform', []],
  ['feature-flags', 1, 'platform', []],
  ['config-service', 2, 'platform', []],
  ['search', 2, 'data', ['restaurant-catalog']],
  ['recommendation', 3, 'data', ['search', 'analytics-ingest']],
  ['analytics-ingest', 3, 'data', []],
  ['reviews', 3, 'data', ['user-profile']],
  ['support-desk', 3, 'platform', ['orders', 'user-profile']],
]

const TEAMS = ['checkout', 'pricing', 'dispatch', 'payments', 'data', 'platform']

// [slug, display name, team]
const PEOPLE: [string, string, string][] = [
  ['arjun', 'Arjun Mehta', 'checkout'],
  ['dana', 'Dana Okafor', 'platform'],
  ['marco', 'Marco Bianchi', 'data'],
  ['rahul', 'Rahul Verma', 'pricing'],
  ['priya', 'Priya Nair', 'pricing'],
  ['wei', 'Wei Zhang', 'pricing'],
  ['leah', 'Leah Cohen', 'checkout'],
  ['tomas', 'Tomás García', 'dispatch'],
  ['kofi', 'Kofi Mensah', 'dispatch'],
  ['ines', 'Ines Duarte', 'payments'],
]

// ---------------------------------------------------------------- source documents

type SourceFixture = Omit<SourceDetail, 'id' | 'conflict'> & { conflict?: boolean }

export const SOURCES: Record<string, SourceFixture> = {
  'adr:011': {
    source: 'adr', title: 'ADR-011: Pricing cache TTL must stay >= 300s', updated_at: ts('2026-02-10T09:00:00Z'),
    access_level: 'internal',
    text: 'Decision: the pricing cache TTL must never be set below 300 seconds.\n\nReason: the vendor tax/price API is rate limited. A short TTL multiplies calls to it and nearly caused an outage. Authored by Marco Bianchi (Pricing).\n\nSupersedes: wiki "Pricing cache: 60s TTL is fine".',
  },
  'inc:INC-0307': {
    source: 'incident', title: 'INC-0307: Pricing overload after cache TTL lowered to 30s', updated_at: ts('2026-03-07T12:00:00Z'),
    access_level: 'internal',
    text: 'Severity P1. Affected: pricing, checkout.\nCaused by PR #211 (cache TTL lowered to 30s), reverted by Marco Bianchi.\nPostmortem: low TTL multiplied vendor calls; pricing latency climbed and checkout timed out.',
  },
  'thread:pricing-private-0142': {
    source: 'slack', title: '#pricing-private: why TTL >= 300s', updated_at: ts('2026-02-09T16:20:00Z'),
    access_level: 'restricted',
    text: 'Marco: the vendor allows 200 req/min on the price API. With a 30s TTL we sit at 190 on a normal day, so a promo spike breaks the limit.\nRahul: agreed, write it up as an ADR and set the floor at 300s.\n(Vendor rate numbers are confidential to the pricing team.)',
  },
  'wiki:pricing-cache': {
    source: 'wiki', title: 'Pricing cache: 60s TTL is fine', updated_at: ts('2025-06-01T09:00:00Z'),
    access_level: 'internal',
    text: 'The pricing cache TTL can be 60 seconds. Lower values are fine if you need prices to refresh faster.\n(Outdated: superseded by ADR-011.)',
  },
  'runbook:pricing-oncall': {
    source: 'runbook', title: 'Runbook: pricing on-call', updated_at: ts('2025-11-20T09:00:00Z'),
    access_level: 'internal', text: 'For pricing incidents, page Marco.\n(Stale: Marco moved to the Data team in August 2026. Page the pricing owner, Rahul.)',
  },
  'pr:482': {
    source: 'github', title: 'PR #482: Lower pricing cache TTL to 5s for faster promo updates', updated_at: ts('2026-10-13T12:40:00Z'),
    access_level: 'internal',
    text: 'Author: Priya Nair. Reviewer: Wei Zhang. Fixes PRC-311.\nChange: pricing/config.yaml cache_ttl_seconds 300 -> 5.\nMotivation: promo price changes took 5 minutes to show.',
  },
  'pr:479': {
    source: 'github', title: 'PR #479: Update checkout button copy', updated_at: ts('2026-10-13T20:30:00Z'),
    access_level: 'internal', text: 'Author: Leah Cohen.\nChange: checkout/i18n/en.json only (button label text). No code or config changes.',
  },
  'ticket:PRC-311': {
    source: 'jira', title: 'PRC-311: Promo price changes take 5 minutes to show', updated_at: ts('2026-10-12T08:00:00Z'),
    access_level: 'internal', text: 'Promo editors see price changes only after the pricing cache expires (TTL 300s). Ask: make it faster.',
  },
  'pr:517': {
    source: 'github', title: 'PR #517: Reduce eta-predictor model cache TTL to 10s', updated_at: ts('2026-10-20T12:10:00Z'),
    access_level: 'internal', text: 'Author: Tomás García.\nChange: eta-predictor/config.yaml model_cache_ttl 300 -> 10.',
  },
}

// ---------------------------------------------------------------- the graph (~67 nodes)

const node = (id: string, label: string, name: string, props: Record<string, unknown> = {}): GraphNode => ({
  id, label, name, access_level: SOURCES[id]?.access_level ?? null, props,
})
const link = (source: string, target: string, type: string): EdgeRef => ({ source, target, type })

export const E = link // short alias used by the scripted events in mock.ts

const nodes: GraphNode[] = [
  ...SERVICES.map(([n, tier, owner]) => node(`svc:${n}`, 'Service', n, { tier, owner })),
  ...TEAMS.map((t) => node(`team:${t}`, 'Team', t)),
  ...PEOPLE.map(([slug, name]) => node(`person:${slug}`, 'Person', name)),
  node('alert:A-3001', 'Alert', 'A-3001: checkout p99 > 3s'),
  node('alert:A-3002', 'Alert', 'A-3002: dispatch latency > 5s'),
  node('deploy:990', 'Deploy', 'Deploy 990'),
  node('deploy:991', 'Deploy', 'Deploy 991'),
  node('deploy:1034', 'Deploy', 'Deploy 1034'),
  node('deploy:1035', 'Deploy', 'Deploy 1035'),
  node('pr:479', 'PR', 'PR #479 button copy'),
  node('pr:482', 'PR', 'PR #482 TTL 300s to 5s'),
  node('pr:517', 'PR', 'PR #517 eta TTL to 10s'),
  node('pr:518', 'PR', 'PR #518 push template typo'),
  node('repo:pricing', 'Repo', 'repo pricing'),
  node('repo:checkout', 'Repo', 'repo checkout'),
  node('mod:pricing/config.yaml', 'CodeModule', 'pricing/config.yaml'),
  node('mod:checkout/i18n/en.json', 'CodeModule', 'checkout/i18n/en.json'),
  node('adr:011', 'Decision', 'ADR-011 TTL >= 300s'),
  node('inc:INC-0307', 'Incident', 'INC-0307 pricing overload'),
  node('ticket:PRC-311', 'Ticket', 'PRC-311 promo delay'),
  node('thread:pricing-private-0142', 'Thread', '#pricing-private thread 0142'),
  node('wiki:pricing-cache', 'Doc', 'wiki: 60s TTL is fine'),
  node('runbook:pricing-oncall', 'Doc', 'runbook: pricing on-call'),
]

const links: EdgeRef[] = [
  ...SERVICES.flatMap(([n, , owner, deps]) => [
    link(`team:${owner}`, `svc:${n}`, 'OWNS'),
    ...deps.map((d) => link(`svc:${n}`, `svc:${d}`, 'DEPENDS_ON')),
  ]),
  ...PEOPLE.map(([slug, , team]) => link(`person:${slug}`, `team:${team}`, 'MEMBER_OF')),
  link('alert:A-3001', 'svc:checkout', 'FIRED_ON'),
  link('alert:A-3002', 'svc:dispatch', 'FIRED_ON'),
  link('deploy:990', 'svc:checkout', 'DEPLOYED_TO'),
  link('deploy:990', 'pr:479', 'INCLUDES'),
  link('deploy:991', 'svc:pricing', 'DEPLOYED_TO'),
  link('deploy:991', 'pr:482', 'INCLUDES'),
  link('deploy:1034', 'svc:eta-predictor', 'DEPLOYED_TO'),
  link('deploy:1034', 'pr:517', 'INCLUDES'),
  link('deploy:1035', 'svc:notifications', 'DEPLOYED_TO'),
  link('deploy:1035', 'pr:518', 'INCLUDES'),
  link('person:leah', 'pr:479', 'AUTHORED'),
  link('person:priya', 'pr:482', 'AUTHORED'),
  link('person:wei', 'pr:482', 'REVIEWED'),
  link('person:tomas', 'pr:517', 'AUTHORED'),
  link('pr:479', 'mod:checkout/i18n/en.json', 'MODIFIES'),
  link('pr:482', 'mod:pricing/config.yaml', 'MODIFIES'),
  link('pr:482', 'ticket:PRC-311', 'FIXES'),
  link('pr:482', 'repo:pricing', 'IN_REPO'),
  link('svc:pricing', 'repo:pricing', 'BUILT_FROM'),
  link('svc:checkout', 'repo:checkout', 'BUILT_FROM'),
  link('repo:pricing', 'mod:pricing/config.yaml', 'CONTAINS'),
  link('repo:checkout', 'mod:checkout/i18n/en.json', 'CONTAINS'),
  link('adr:011', 'thread:pricing-private-0142', 'DISCUSSED_IN'),
  link('adr:011', 'wiki:pricing-cache', 'SUPERSEDES'),
  link('inc:INC-0307', 'svc:pricing', 'AFFECTED'),
  link('inc:INC-0307', 'svc:checkout', 'AFFECTED'),
  link('inc:INC-0307', 'person:marco', 'RESOLVED_BY'),
  link('person:marco', 'svc:pricing', 'EXPERT_IN'),
  link('inc:INC-0307', 'adr:011', 'RECORDED_IN'),
  link('wiki:pricing-cache', 'svc:pricing', 'MENTIONS'),
  link('runbook:pricing-oncall', 'svc:pricing', 'MENTIONS'),
  link('ticket:PRC-311', 'svc:pricing', 'MENTIONS'),
]

/** Permission-filtered copy of the graph, like GET /api/graph would return for this persona. */
export function graphFor(personaId: string): GraphView {
  const visible = nodes.filter((n) => canSee(personaId, n.id))
  const ids = new Set(visible.map((n) => n.id))
  return {
    nodes: visible.map((n) => ({ ...n })),
    links: links.filter((l) => ids.has(l.source) && ids.has(l.target)).map((l) => ({ ...l })),
  }
}
