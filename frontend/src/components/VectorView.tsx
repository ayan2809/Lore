// Graph OFF (vector-only) view of the company: the same documents as separate squares, grouped
// by type, with no links between them. The documents a search step returned light up, numbered
// by rank. Design: canvas "Lore Investigation Screen", artboard "Graph OFF".

import type { GraphView } from '../api/types'
import type { ToolItem, TrailItem } from '../hooks/investigationState'
import { agentStyle, isSourceLabel, labelFromId, nodeColor } from '../lib/format'

interface Props {
  graph: GraphView | null
  loading: boolean
  trail: TrailItem[]
  selectedSeq: number | null
  onOpenSource: (id: string) => void
  compact?: boolean // the comparison view: no banner, no search card
}

// Labels that have text, so vector search can find them (backend lore/loader/chunk.py SOURCE_LABELS).
const GROUPS: { label: string; name: string }[] = [
  { label: 'PR', name: 'PRs' },
  { label: 'Thread', name: 'Slack threads' },
  { label: 'Ticket', name: 'Tickets' },
  { label: 'Doc', name: 'Docs and runbooks' },
  { label: 'Incident', name: 'Incidents' },
  { label: 'Decision', name: 'Decisions (ADRs)' },
]
const NO_TEXT_NAMES: Record<string, [string, string]> = {
  Service: ['service', 'services'],
  Deploy: ['deploy', 'deploys'],
  Repo: ['repo', 'repos'],
  CodeModule: ['code module', 'code modules'],
  Team: ['team', 'teams'],
  Person: ['person', 'people'],
}
// Steps that search by text: these are what the view follows during a run.
const SEARCH_TOOLS = new Set(['search_discussions', 'similar_incidents', 'find_entity'])

export default function VectorView({ graph, loading, trail, selectedSeq, onOpenSource, compact }: Props) {
  const tools = trail.filter((t): t is ToolItem => t.kind === 'tool' && t.nodeIds.length > 0)
  const searches = tools.filter((t) => SEARCH_TOOLS.has(t.tool))
  const active = selectedSeq !== null ? tools.find((t) => t.seq === selectedSeq) : searches[searches.length - 1]
  const rank = new Map((compact ? [] : (active?.nodeIds ?? [])).map((id, i) => [id, i + 1]))
  const seen = new Set(searches.flatMap((t) => t.nodeIds))

  // Every document: the loaded view plus anything a search found outside it.
  const names = new Map<string, string>()
  const labels = new Map<string, string>()
  for (const n of graph?.nodes ?? []) {
    names.set(n.id, n.name)
    labels.set(n.id, n.label)
  }
  for (const t of tools) for (const id of t.nodeIds) if (!labels.has(id)) labels.set(id, labelFromId(id))
  const groups = GROUPS.map((g) => ({
    ...g,
    ids: [...labels].filter(([, l]) => l === g.label).map(([id]) => id).filter((id) => !compact || seen.has(id)),
  })).filter((g) => g.ids.length > 0)

  const noText = Object.entries(NO_TEXT_NAMES)
    .map(([label, [one, many]]) => {
      const n = [...labels.values()].filter((l) => l === label).length
      return n ? `${n} ${n === 1 ? one : many}` : ''
    })
    .filter(Boolean)

  return (
    <div className="flex h-full min-h-[24rem] w-full flex-col overflow-hidden rounded-xl border border-slate-800 bg-[#050b1a]">
      {!compact && (
        <div className="mx-3 mt-3 flex flex-wrap items-start gap-x-3 gap-y-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5">
          <span className="rounded-md bg-slate-700 px-2 py-0.5 text-xs font-bold tracking-wide text-slate-100">
            GRAPH OFF · VECTOR SEARCH ONLY
          </span>
          <p className="min-w-[16rem] flex-1 text-[13px] text-slate-300">
            Lore sees Kettle as separate documents and finds them only by how close their text is to the question. With no
            links it cannot compute a blast radius, follow a deploy to its PR, draw an evidence path or find owners.
          </p>
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-4 pb-2 pt-4">
        {loading && <p className="text-sm text-slate-400">Loading documents...</p>}
        {!loading && !graph && <p className="text-sm text-slate-500">Documents unavailable</p>}
        {compact && groups.length === 0 && <p className="text-sm text-slate-500">No documents retrieved yet.</p>}
        {groups.map((g) => (
          <div key={g.label}>
            <div className="mb-1.5 flex items-baseline gap-2 text-xs">
              <span className="size-2 rounded-sm" style={{ backgroundColor: nodeColor(g.label) }} />
              <span className="font-semibold text-slate-200">{g.name}</span>
              <span className="text-slate-500">{g.ids.length}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {g.ids.map((id) => {
                const r = rank.get(id)
                const color = nodeColor(g.label)
                const style = r
                  ? { backgroundColor: color, boxShadow: `0 0 0 2px #050b1a, 0 0 0 3px #e0f2fe, 0 0 12px ${color}` }
                  : { backgroundColor: color, opacity: seen.has(id) ? 0.6 : 0.18 }
                return (
                  <button
                    key={id}
                    title={`${names.get(id) ?? id} (${id})`}
                    aria-label={`${names.get(id) ?? id}${r ? `, result ${r}` : ''}`}
                    onClick={() => isSourceLabel(g.label) && onOpenSource(id)}
                    className="grid size-3.5 place-items-center rounded-[3px] text-[9px] font-bold text-slate-950 transition-opacity duration-300"
                    style={style}
                  >
                    {r ?? ''}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        {!compact && noText.length > 0 && (
          <p className="text-xs text-slate-500">No text, so not searchable here: {noText.join(', ')}.</p>
        )}
      </div>

      {!compact && active && (
        <div className="mx-3 mb-3 rounded-lg border border-slate-800 bg-slate-950/90 p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-xs font-semibold capitalize ring-1 ${agentStyle(active.agent)}`}>
              {active.agent ?? 'system'}
            </span>
            <span className="font-mono text-sm font-semibold text-slate-100">{active.tool}</span>
            <span className="ml-auto text-xs text-slate-400">ranked by similarity</span>
          </div>
          {active.reason && <p className="mb-2 text-[13px] text-slate-300">“{active.reason}”</p>}
          <ol className="grid grid-cols-1 gap-x-4 gap-y-1 text-[13px] sm:grid-cols-2">
            {active.nodeIds.map((id, i) => (
              <li key={id} className="flex min-w-0 items-center gap-2">
                <span className="w-4 text-right font-semibold tabular-nums text-slate-500">{i + 1}</span>
                <span className="size-2 flex-none rounded-sm" style={{ backgroundColor: nodeColor(labels.get(id) ?? labelFromId(id)) }} />
                <button
                  onClick={() => onOpenSource(id)}
                  className="truncate text-left text-slate-200 hover:text-sky-300"
                  title={id}
                >
                  {names.get(id) && names.get(id) !== id ? `${names.get(id)} · ${id}` : id}
                </button>
              </li>
            ))}
          </ol>
          {active.restrictedMatches > 0 && (
            <p className="mt-2 text-xs text-amber-300">{active.restrictedMatches} restricted match(es) hidden from you</p>
          )}
        </div>
      )}
      {!compact && !active && graph && (
        <p className="mx-4 mb-4 text-sm text-slate-500">Run the incident to see what text search finds.</p>
      )}
    </div>
  )
}
