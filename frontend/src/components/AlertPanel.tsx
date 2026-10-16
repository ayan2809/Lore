import type { AlertItem } from '../api/types'
import type { InvestigationState } from '../hooks/investigationState'
import { Panel } from './ui'

interface Props {
  alerts: AlertItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  status: InvestigationState['status']
  personaName: string
  replay: boolean
  onReplay: (value: boolean) => void
  onRun: () => void
}

export default function AlertPanel({ alerts, selectedId, onSelect, status, personaName, replay, onReplay, onRun }: Props) {
  const busy = status === 'starting' || status === 'running'
  const ran = status === 'done' || status === 'failed'
  const first = personaName.split(' ')[0]

  return (
    <Panel title="Alerts">
      <ul className="space-y-2">
        {alerts.map((a) => (
          <li key={a.id}>
            <button
              onClick={() => onSelect(a.id)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition ${
                a.id === selectedId ? 'border-red-500/60 bg-red-500/10' : 'border-slate-700 bg-slate-900 hover:border-slate-600'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm font-semibold text-red-300">{a.name}</span>
                <span className="text-xs text-slate-500">
                  {new Date(a.started_at * 1000).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}
                </span>
              </div>
              <div className="mt-0.5 text-sm text-slate-200">{a.symptom}</div>
              <div className="font-mono text-xs text-slate-500">{a.service}</div>
            </button>
          </li>
        ))}
        {alerts.length === 0 && <li className="text-sm text-slate-500">No alerts (is the backend running?)</li>}
      </ul>

      <button
        onClick={onRun}
        disabled={busy || !selectedId}
        className="mt-4 w-full rounded-xl bg-red-600 px-4 py-3.5 text-lg font-bold text-white shadow-lg shadow-red-900/40 transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Agents working...' : ran ? `▶ Run again as ${first}` : '▶ Run the 3 AM incident'}
      </button>

      <label className="mt-3 flex items-center gap-2 text-xs text-slate-400" title="Play back a recorded run instead of calling Gemini">
        <input type="checkbox" checked={replay} onChange={(e) => onReplay(e.target.checked)} className="accent-sky-500" />
        Replay a recorded run (no live Gemini)
      </label>
    </Panel>
  )
}
