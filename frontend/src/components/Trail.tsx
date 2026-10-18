import { useEffect, useRef, useState } from 'react'
import type { InvestigationState, TrailItem } from '../hooks/investigationState'
import { agentStyle, formatMs } from '../lib/format'
import { CitationList } from './CitationChip'

interface Props {
  trail: TrailItem[]
  status: InvestigationState['status']
  activeSeq: number | null // the step currently highlighted in the graph
  selectedSeq: number | null // true when the user clicked a step (not just "latest")
  onSelect: (seq: number | null) => void
  onOpenSource: (id: string) => void
}

function AgentBadge({ agent }: { agent: string | null }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold capitalize ring-1 ${agentStyle(agent)}`}>
      {agent ?? 'system'}
    </span>
  )
}

function ToolRow({
  item, active, onSelect,
}: {
  item: Extract<TrailItem, { kind: 'tool' }>
  active: boolean
  onSelect: () => void
}) {
  const [showCypher, setShowCypher] = useState(false)
  const failed = item.status === 'error'
  const running = item.status === 'running'
  const canHighlight = item.nodeIds.length > 0

  return (
    <div
      className={`rounded-lg border px-3 py-2 text-sm transition ${
        failed
          ? 'border-red-500/50 bg-red-500/10'
          : active
            ? 'border-sky-500/60 bg-sky-500/10'
            : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
      } ${canHighlight ? 'cursor-pointer' : ''}`}
      onClick={canHighlight ? onSelect : undefined}
    >
      <div className="flex items-center gap-2">
        <AgentBadge agent={item.agent} />
        <span className="font-mono font-semibold text-slate-100">{item.tool}</span>
        <span className="ml-auto flex items-center gap-2 text-xs text-slate-400">
          {running ? (
            <span className="animate-pulse text-sky-300">running...</span>
          ) : (
            <>
              <span>{item.rowCount} rows</span>
              <span className="font-mono">{formatMs(item.ms)}</span>
            </>
          )}
        </span>
      </div>
      <p className="mt-1 text-slate-300">{item.reason}</p>

      {failed && <p className="mt-1 font-medium text-red-300">Error: {item.error}</p>}
      {item.restrictedMatches > 0 && (
        <p className="mt-1 text-xs text-amber-300">{item.restrictedMatches} restricted match(es) hidden from you</p>
      )}

      {item.cypher && (
        <div className="mt-1.5" onClick={(e) => e.stopPropagation()}>
          <button onClick={() => setShowCypher(!showCypher)} className="text-xs text-sky-400 hover:text-sky-300">
            {showCypher ? 'Hide Cypher' : 'Show Cypher'}
          </button>
          {showCypher && (
            <pre className="mt-1 overflow-x-auto rounded-md bg-slate-950 p-2 font-mono text-xs leading-relaxed text-emerald-300">
              {item.cypher}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

export default function Trail({ trail, status, activeSeq, selectedSeq, onSelect, onOpenSource }: Props) {
  const scroller = useRef<HTMLDivElement>(null)

  // Follow the newest step while the run is live (but not if the user clicked an older one).
  useEffect(() => {
    const el = scroller.current
    if (el && selectedSeq === null) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [trail.length, selectedSeq])

  // This panel scrolls on its own, so the alert button above it stays visible.
  return (
    <section className="flex max-h-[36rem] min-h-0 flex-col rounded-xl border border-slate-800 bg-slate-900/60 lg:max-h-none lg:flex-1">
      <div className="flex items-center justify-between px-4 pt-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Reasoning trail</h2>
        {selectedSeq !== null && (
          <button onClick={() => onSelect(null)} className="text-xs text-sky-400 hover:text-sky-300">
            Follow latest
          </button>
        )}
      </div>
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto p-4 pt-3">
        {trail.length === 0 && (
          <p className="text-sm text-slate-500">
            {status === 'starting' ? 'Starting...' : 'Every tool call the agents make appears here, with the Cypher they ran.'}
          </p>
        )}
        <div className="space-y-2">
          {trail.map((item) => {
            switch (item.kind) {
              case 'agent':
                return (
                  <div key={item.seq} className="flex items-center gap-2 pt-2 text-sm">
                    <AgentBadge agent={item.agent} />
                    <span className="text-slate-300">{item.goal}</span>
                    {item.done && item.confidence !== undefined && (
                      <span className="ml-auto text-xs text-slate-500">{Math.round(item.confidence * 100)}%</span>
                    )}
                  </div>
                )
              case 'tool':
                return <ToolRow key={item.seq} item={item} active={item.seq === activeSeq} onSelect={() => onSelect(item.seq)} />
              case 'finding':
                return (
                  <div key={item.seq} className="rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2 text-sm">
                    <p className="text-slate-100">{item.text}</p>
                    <div className="mt-1.5">
                      <CitationList ids={item.citations} onOpen={onOpenSource} />
                    </div>
                  </div>
                )
              case 'notice':
                return (
                  <div
                    key={item.seq}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      item.level === 'blocked'
                        ? 'border-red-500/50 bg-red-500/10 text-red-200'
                        : item.level === 'info'
                          ? 'border-sky-500/50 bg-sky-500/10 text-sky-200'
                          : 'border-amber-500/50 bg-amber-500/10 text-amber-200'
                    }`}
                  >
                    {item.level === 'blocked' ? 'Policy blocked: ' : item.level === 'info' ? 'Note: ' : 'Error: '}
                    {item.message}
                  </div>
                )
            }
          })}
        </div>
      </div>
    </section>
  )
}
