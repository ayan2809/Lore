// Graph ON vs Graph OFF for the same alert and viewer, side by side (design: canvas "Lore
// Investigation Screen", artboard "Compare"). Every value comes from the two runs' reports and
// summaries; nothing here is computed by a model.

import type { ReactNode } from 'react'
import type { GraphView } from '../api/types'
import type { EdgeRef } from '../api/types'
import type { Highlights, InvestigationState } from '../hooks/investigationState'
import { displayName, formatCost, formatMs } from '../lib/format'
import GraphCanvas from './GraphCanvas'
import VectorView from './VectorView'

interface Side {
  state: InvestigationState
  highlights: Highlights
  discovered: { nodeIds: string[]; edges: EdgeRef[] }
}

interface Props {
  alertLabel: string
  personaName: string
  on: Side
  off: Side
  graph: GraphView | null
  loading: boolean
  busy: boolean
  onRunAgain: () => void
  onBack: () => void
  onOpenFull: (mode: 'graph' | 'vector') => void
  onOpenSource: (id: string) => void
}

type Cell = { text: ReactNode; tone?: 'good' | 'bad' }

const toneClass = (tone?: 'good' | 'bad') => (tone === 'good' ? 'text-sky-300' : tone === 'bad' ? 'text-orange-300' : 'text-slate-200')

function rows(s: InvestigationState): Record<string, Cell> {
  const r = s.report
  const m = s.summary
  const pending: Cell = { text: s.status === 'failed' ? 'run failed' : s.status === 'idle' ? '' : 'running…' }
  if (!r) {
    const p = { ...pending }
    return { root: p, ruled: p, severity: p, path: p, page: p, tools: p, calls: p, ttrc: p, cost: p, conf: p, restricted: p }
  }
  // the change each rejected claim is about: its PR if it cites one (a claim can cite the deploy first)
  const ruled = [
    ...new Set(r.rejected_suspects.map((c) => c.citations.find((i) => i.startsWith('pr:')) ?? c.citations[0]).filter(Boolean)),
  ]
  return {
    root: r.root_cause ? { text: <b className="font-mono text-slate-100">{r.root_cause}</b> } : { text: 'not found', tone: 'bad' },
    ruled: ruled.length ? { text: <span className="font-mono text-[13px]">{ruled.join(', ')}</span> } : { text: 'nothing', tone: 'bad' },
    severity: r.severity ? { text: `${r.severity}, set by rule from the blast radius`, tone: 'good' } : { text: 'none: no blast radius without links', tone: 'bad' },
    path: r.evidence_path.length
      ? { text: <span className="font-mono text-[13px]">{r.evidence_path.join(' › ')}</span>, tone: 'good' }
      : { text: 'none', tone: 'bad' },
    page: r.people.page ? { text: displayName(r.people.page), tone: 'good' } : { text: 'nobody named', tone: 'bad' },
    tools: { text: m ? String(m.steps) : '…' },
    calls: { text: m ? String(m.model_calls) : '…' },
    ttrc: { text: m ? (m.time_to_root_cause_ms === null ? 'not found' : formatMs(m.time_to_root_cause_ms)) : '…' },
    cost: { text: m ? formatCost(m.cost_usd) : '…' },
    conf: { text: `${Math.round(r.confidence * 100)}%` },
    restricted: { text: String(r.restricted_matches) },
  }
}

const LABELS: [string, string][] = [
  ['root', 'Root cause'],
  ['ruled', 'Suspects ruled out'],
  ['severity', 'Severity'],
  ['path', 'Evidence path'],
  ['page', 'Who to page'],
  ['tools', 'Tool calls'],
  ['calls', 'Model calls'],
  ['ttrc', 'Time to root cause'],
  ['cost', 'Cost of the run'],
  ['conf', 'Confidence'],
  ['restricted', 'Restricted matches hidden'],
]

/** Lower is better for these; mark the cheaper/faster side once both runs are done. */
function better(key: string, a: InvestigationState, b: InvestigationState): 'on' | 'off' | null {
  const x = a.summary
  const y = b.summary
  if (!x || !y) return null
  const pick = (u: number | null, v: number | null) => (u === null || v === null || u === v ? null : u < v ? 'on' : 'off')
  if (key === 'ttrc') return pick(x.time_to_root_cause_ms, y.time_to_root_cause_ms)
  if (key === 'cost') return pick(x.cost_usd, y.cost_usd)
  if (key === 'tools') return pick(x.steps, y.steps)
  if (key === 'calls') return pick(x.model_calls, y.model_calls)
  return null
}

export default function CompareView({
  alertLabel, personaName, on, off, graph, loading, busy, onRunAgain, onBack, onOpenFull, onOpenSource,
}: Props) {
  const a = rows(on.state)
  const b = rows(off.state)
  const replay = on.state.replay || off.state.replay

  return (
    <div className="mx-auto flex max-w-[1360px] flex-col gap-5 px-4 pb-10 pt-6">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="min-w-[18rem] flex-1">
          <h2 className="text-2xl font-bold tracking-tight text-white">Graph ON vs Graph OFF</h2>
          <p className="text-slate-400">
            {alertLabel} · viewing as {personaName} · {replay ? 'recorded runs' : 'live runs'}, same alert, same agents and models
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRunAgain}
            disabled={busy}
            className="min-h-11 rounded-lg border border-slate-700 bg-slate-900 px-4 font-semibold text-slate-100 hover:border-slate-500 disabled:opacity-50"
          >
            {busy ? 'Both running…' : 'Run both again'}
          </button>
          <button onClick={onBack} className="min-h-11 rounded-lg px-3 text-slate-400 hover:text-slate-200">
            Back to one run
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
        <table className="w-full min-w-[44rem] border-collapse text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wider">
              <th className="w-1/4 px-3.5 py-2.5" />
              <th className="px-3.5 py-2.5 text-left font-bold text-sky-300">Graph ON</th>
              <th className="px-3.5 py-2.5 text-left font-bold text-slate-300">Graph OFF · vector only</th>
            </tr>
          </thead>
          <tbody>
            {LABELS.map(([key, label]) => {
              const win = better(key, on.state, off.state)
              return (
                <tr key={key} className="border-t border-slate-800 align-top">
                  <th className="px-3.5 py-2.5 text-left font-medium text-slate-400">{label}</th>
                  <td className={`px-3.5 py-2.5 tabular-nums ${win === 'on' ? 'text-sky-300' : toneClass(a[key].tone)}`}>{a[key].text}</td>
                  <td className={`px-3.5 py-2.5 tabular-nums ${win === 'off' ? 'text-sky-300' : toneClass(b[key].tone)}`}>{b[key].text}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-4">
        {(
          [
            ['graph', on, 'GRAPH ON', 'the graph the agents walked', 'bg-sky-500/20 text-sky-300'],
            ['vector', off, 'GRAPH OFF', 'every document the searches returned', 'bg-slate-700 text-slate-100'],
          ] as const
        ).map(([mode, side, chip, caption, chipClass]) => (
          <section key={mode} className="flex min-w-0 flex-[1_1_26rem] flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center gap-2">
              <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${chipClass}`}>{chip}</span>
              <span className="text-[13px] text-slate-400">{caption}</span>
            </div>
            <div className="h-[22rem]">
              {mode === 'graph' ? (
                <GraphCanvas
                  graph={graph}
                  loading={loading}
                  discovered={side.discovered}
                  highlights={side.highlights}
                  graphOn
                  onOpenSource={onOpenSource}
                />
              ) : (
                <VectorView graph={graph} loading={loading} trail={side.state.trail} selectedSeq={null} onOpenSource={onOpenSource} compact />
              )}
            </div>
            <p className="text-slate-200">{side.state.report?.summary ?? (side.state.status === 'idle' ? '' : 'The report appears when the agents finish.')}</p>
            <button onClick={() => onOpenFull(mode)} className="self-start text-[13px] text-sky-400 hover:text-sky-300">
              Open the full {mode === 'graph' ? 'Graph ON' : 'Graph OFF'} run
            </button>
          </section>
        ))}
      </div>

      <p className="text-[13px] text-slate-500">
        Graph OFF varies more from run to run than Graph ON. A live comparison runs both at once and uses two of today&apos;s live runs.
      </p>
    </div>
  )
}
