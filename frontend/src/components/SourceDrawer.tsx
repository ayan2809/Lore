import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { SourceDetail } from '../api/types'
import { formatDate } from '../lib/format'
import { AccessBadge } from './ui'

type Load = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ok'; source: SourceDetail }
type Result = { id: string; load: Load }

/** Slide-in panel that shows one source (GET /api/sources/{id}). Closed when `id` is null. */
export default function SourceDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  // Remember which id the result belongs to; a result for another id counts as "still loading".
  const [result, setResult] = useState<Result | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    api
      .getSource(id)
      .then((source) => !cancelled && setResult({ id, load: { status: 'ok', source } }))
      .catch((err: Error) => !cancelled && setResult({ id, load: { status: 'error', message: err.message } }))
    return () => {
      cancelled = true
    }
  }, [id])

  if (!id) return null
  const load: Load = result?.id === id ? result.load : { status: 'loading' }
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-lg flex-col border-l border-slate-700 bg-slate-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-800 p-4">
          <div>
            <div className="font-mono text-sm text-sky-300">{id}</div>
            {load.status === 'ok' && <div className="mt-1 text-base font-medium text-slate-100">{load.source.title}</div>}
          </div>
          <button onClick={onClose} className="rounded px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white">
            Close
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {load.status === 'loading' && <p className="text-slate-400">Loading...</p>}
          {load.status === 'error' && (
            <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
              Cannot show this source: {load.message}. It may not exist, or you may not have access.
            </p>
          )}
          {load.status === 'ok' && (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <AccessBadge level={load.source.access_level} />
                <span className="rounded bg-slate-800 px-1.5 py-0.5">{load.source.source}</span>
                {load.source.updated_at && <span>updated {formatDate(load.source.updated_at)}</span>}
                {load.source.conflict && (
                  <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-orange-300 ring-1 ring-orange-500/40">
                    conflicts with a higher-ranked source
                  </span>
                )}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{load.source.text}</p>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
