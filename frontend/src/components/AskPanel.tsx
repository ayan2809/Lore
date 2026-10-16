import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api/client'
import type { AskAnswer, GraphMode } from '../api/types'
import { formatDate, formatMs, restrictedMessage } from '../lib/format'
import CitationChip, { CitationList } from './CitationChip'
import { AccessBadge, Panel, RestrictedWarning } from './ui'

const EXAMPLES = [
  'Why is the pricing cache TTL 300 seconds?',
  'Who knows the ledger service?',
  'Why was Marco transferred to the data team?', // refused by the request policy
]

export default function AskPanel({ mode, personaName, onOpenSource }: { mode: GraphMode; personaName: string; onOpenSource: (id: string) => void }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ask = async (q: string) => {
    if (!q.trim()) return
    setQuestion(q)
    setBusy(true)
    setError(null)
    try {
      setAnswer(await api.ask({ question: q, mode }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    ask(question)
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-4">
      <Panel
        title="Ask the brain"
        right={<span className="text-xs text-slate-400">as {personaName} · Graph {mode === 'graph' ? 'ON' : 'OFF'}</span>}
      >
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask anything about Kettle's code, decisions and people..."
            className="flex-1 rounded-lg border border-slate-600 bg-slate-950 px-3 py-2.5 text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
          />
          <button disabled={busy || !question.trim()} className="rounded-lg bg-sky-600 px-5 font-semibold text-white hover:bg-sky-500 disabled:opacity-50">
            {busy ? 'Thinking...' : 'Ask'}
          </button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => ask(ex)} className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-sky-500 hover:text-white">
              {ex}
            </button>
          ))}
        </div>
      </Panel>

      {error && <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}

      {answer && (
        <Panel title="Answer" right={<span className="font-mono text-xs text-slate-500">{formatMs(answer.ms)}</span>}>
          {answer.restricted_matches > 0 && (
            <div className="mb-3">
              <RestrictedWarning text={restrictedMessage(answer.restricted_matches, answer.restricted_owner_hint)} />
            </div>
          )}

          {answer.refused ? (
            <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
              <span className="font-semibold">Refused by policy. </span>
              {/* the backend puts the reason in claims[0].text */}
              {answer.claims[0]?.text ?? 'Lore will not answer this kind of question.'}
            </p>
          ) : answer.claims.length === 0 ? (
            <p className="text-sm text-slate-400">No cited answer found in the sources you can see.</p>
          ) : (
            <ul className="space-y-3">
              {answer.claims.map((c, i) => (
                <li key={i} className="text-base leading-relaxed text-slate-100">
                  {c.text} <CitationList ids={c.citations} onOpen={onOpenSource} />
                </li>
              ))}
            </ul>
          )}

          {answer.sources.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Sources used</h3>
              <ul className="space-y-1.5">
                {answer.sources.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <CitationChip id={s.id} onOpen={onOpenSource} />
                    <span className="text-slate-300">{s.title}</span>
                    <AccessBadge level={s.access_level} />
                    {s.updated_at && <span className="text-xs text-slate-500">{formatDate(s.updated_at)}</span>}
                    {s.conflict && (
                      <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-xs font-semibold text-orange-300 ring-1 ring-orange-500/40">
                        CONFLICT: outranked by a newer or higher-ranked source
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
      )}
    </div>
  )
}
