// Small display helpers: colours per node label / agent, and text formatting.

export const NODE_COLORS: Record<string, string> = {
  Service: '#38bdf8',
  Person: '#f472b6',
  Team: '#a78bfa',
  PR: '#34d399',
  Deploy: '#fb923c',
  Alert: '#f87171',
  Incident: '#fb7185',
  Decision: '#facc15',
  Thread: '#94a3b8',
  Ticket: '#22d3ee',
  Doc: '#cbd5e1',
  Repo: '#64748b',
  CodeModule: '#475569',
  Role: '#c084fc',
  Channel: '#818cf8',
  Playbook: '#2dd4bf',
}
export const DEFAULT_NODE_COLOR = '#64748b'

export const nodeColor = (label: string) => NODE_COLORS[label] ?? DEFAULT_NODE_COLOR

/** Labels whose nodes are readable sources (GET /api/sources/{id} works for these). */
const SOURCE_LABELS = new Set(['PR', 'Thread', 'Ticket', 'Doc', 'Decision', 'Incident'])
export const isSourceLabel = (label: string) => SOURCE_LABELS.has(label)

// The graph view only knows nodes it was sent. Tool results can mention other ids, so we
// guess a label from the id prefix ("pr:482" -> PR) to colour those nodes.
const PREFIX_LABELS: Record<string, string> = {
  svc: 'Service',
  person: 'Person',
  team: 'Team',
  role: 'Role',
  channel: 'Channel',
  repo: 'Repo',
  mod: 'CodeModule',
  pr: 'PR',
  deploy: 'Deploy',
  ticket: 'Ticket',
  thread: 'Thread',
  wiki: 'Doc',
  runbook: 'Doc',
  pm: 'Doc',
  adr: 'Decision',
  inc: 'Incident',
  alert: 'Alert',
  playbook: 'Playbook',
}
export const labelFromId = (id: string) => PREFIX_LABELS[id.split(':')[0]] ?? 'Doc'

/** "person:rahul" -> "Rahul" ; "pr:482" -> "pr:482" (only people get prettified). */
export function displayName(id: string): string {
  if (id.startsWith('person:')) {
    const slug = id.slice('person:'.length)
    return slug.charAt(0).toUpperCase() + slug.slice(1)
  }
  return id
}

export const AGENT_STYLES: Record<string, string> = {
  triage: 'bg-sky-500/15 text-sky-300 ring-sky-500/40',
  historian: 'bg-violet-500/15 text-violet-300 ring-violet-500/40',
  investigator: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40',
  responder: 'bg-pink-500/15 text-pink-300 ring-pink-500/40',
}
export const agentStyle = (agent: string | null) =>
  (agent && AGENT_STYLES[agent]) || 'bg-slate-500/15 text-slate-300 ring-slate-500/40'

export function formatMs(ms: number): string {
  if (ms < 1) return `${ms.toFixed(2)} ms`
  if (ms < 1000) return `${Math.round(ms)} ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

export const formatCost = (usd: number) => `$${usd < 0.1 ? usd.toFixed(4) : usd.toFixed(2)}`

export function formatDate(unixSeconds: number | null): string {
  if (!unixSeconds) return ''
  return new Date(unixSeconds * 1000).toLocaleString('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

/** Restricted-match warning text. The hint may or may not already start with "ask". */
export function restrictedMessage(count: number, hint: string | null | undefined): string {
  const noun = count === 1 ? 'restricted source' : 'restricted sources'
  const ask = hint ? (/^ask\b/i.test(hint) ? hint : `ask ${hint}`) : 'ask the owning team for access'
  return `${count} ${noun} matched — ${ask}`
}
