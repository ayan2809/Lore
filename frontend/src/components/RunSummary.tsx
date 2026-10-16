import type { GraphMode, RunSummary as Summary } from '../api/types'
import { formatCost, formatMs } from '../lib/format'
import { Panel } from './ui'

function Stat({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="rounded-lg bg-slate-800/70 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`font-mono font-semibold text-slate-100 ${big ? 'text-xl text-emerald-300' : 'text-base'}`}>{value}</div>
    </div>
  )
}

export default function RunSummary({ summary, mode }: { summary: Summary | null; mode: GraphMode }) {
  if (!summary) return null
  return (
    <Panel
      title="Run summary"
      right={
        <div className="flex gap-1.5">
          {summary.replay && (
            <span className="rounded bg-amber-500/20 px-2 py-0.5 text-xs font-bold tracking-wide text-amber-300">REPLAY</span>
          )}
          <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">Graph {mode === 'graph' ? 'ON' : 'OFF'}</span>
        </div>
      }
    >
      <div className="grid grid-cols-2 gap-2">
        <Stat
          label="Time to root cause"
          value={summary.time_to_root_cause_ms === null ? 'not found' : formatMs(summary.time_to_root_cause_ms)}
          big
        />
        <Stat label="Total time" value={formatMs(summary.total_ms)} />
        <Stat label="Tool steps" value={String(summary.steps)} />
        <Stat label="Model calls" value={String(summary.model_calls)} />
        <Stat label="Tokens in / out" value={`${summary.tokens_in.toLocaleString()} / ${summary.tokens_out.toLocaleString()}`} />
        <Stat label="Cost" value={formatCost(summary.cost_usd)} />
      </div>
      <p className="mt-2 text-xs text-slate-500">Kettle today: median 47 min to find the cause.</p>
    </Panel>
  )
}
