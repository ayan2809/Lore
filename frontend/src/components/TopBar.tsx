import type { GraphMode, Health, Persona } from '../api/types'

export type Tab = 'investigate' | 'ask'

interface Props {
  personas: Persona[]
  persona: Persona | null
  onPersona: (id: string) => void
  mode: GraphMode
  onMode: (mode: GraphMode) => void
  health: Health | null // null = backend not reachable
  tab: Tab
  onTab: (tab: Tab) => void
  mock: boolean
}

function Dot({ ok, label, warn }: { ok: boolean; label: string; warn?: boolean }) {
  const colour = ok ? (warn ? 'bg-amber-400' : 'bg-emerald-400') : 'bg-red-500'
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-400" title={`${label}: ${ok ? 'ok' : 'down'}`}>
      <span className={`size-2 rounded-full ${colour}`} />
      {label}
    </span>
  )
}

export default function TopBar({ personas, persona, onPersona, mode, onMode, health, tab, onTab, mock }: Props) {
  const graphOn = mode === 'graph'
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-slate-800 bg-slate-950 px-4 py-2.5">
      <div className="flex items-baseline gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-white">Lore</h1>
        <span className="hidden text-xs text-slate-500 xl:inline">the company brain for 3 AM incidents</span>
        {mock && <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs font-semibold text-amber-300">MOCK DATA</span>}
      </div>

      <nav className="flex rounded-lg bg-slate-900 p-0.5 text-sm">
        {(['investigate', 'ask'] as const).map((t) => (
          <button
            key={t}
            onClick={() => onTab(t)}
            className={`rounded-md px-3 py-1 font-medium transition ${
              tab === t ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t === 'investigate' ? 'Investigate' : 'Ask the brain'}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-2">
        {/* Graph ON/OFF: OFF is the vector-only baseline used in the evaluation */}
        <button
          onClick={() => onMode(graphOn ? 'vector' : 'graph')}
          className="flex items-center gap-2 text-sm text-slate-300"
          title="Graph OFF = vector search only (the baseline)"
        >
          Graph
          <span className={`relative h-5 w-10 rounded-full transition ${graphOn ? 'bg-sky-500' : 'bg-slate-700'}`}>
            <span className={`absolute top-0.5 size-4 rounded-full bg-white transition-all ${graphOn ? 'left-5' : 'left-0.5'}`} />
          </span>
          <span className={`w-8 text-left font-semibold ${graphOn ? 'text-sky-300' : 'text-slate-500'}`}>
            {graphOn ? 'ON' : 'OFF'}
          </span>
        </button>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          Viewing as
          <select
            value={persona?.id ?? ''}
            onChange={(e) => onPersona(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 focus:border-sky-500 focus:outline-none"
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.employment === 'contractor' ? 'contractor' : p.role.split(',')[0]})
              </option>
            ))}
          </select>
        </label>
        {persona && <span className="hidden max-w-xs text-xs text-slate-500 2xl:inline">can see: {persona.can_see}</span>}

        <div className="flex items-center gap-3">
          <Dot ok={health !== null} label="api" />
          <Dot ok={health?.falkordb ?? false} label="falkordb" />
          <Dot ok={health?.gemini ?? false} label="gemini" />
          {/* replay=true means Gemini is bypassed: shown amber so it is never a surprise on video */}
          <Dot ok={health !== null} warn={health?.replay} label={health?.replay ? 'replay ON' : 'live'} />
        </div>
      </div>
    </header>
  )
}
