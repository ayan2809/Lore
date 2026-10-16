import { useState } from 'react'
import { api } from '../api/client'
import type { Action, ActionKind, ActionStatus } from '../api/types'
import { CitationList } from './CitationChip'
import { Panel } from './ui'

const KIND_LABEL: Record<ActionKind, string> = {
  slack_post: 'Slack post',
  github_issue: 'GitHub issue',
  rollback: 'Rollback',
}

const STATUS_STYLE: Record<ActionStatus, string> = {
  proposed: 'bg-sky-500/15 text-sky-300 ring-sky-500/40',
  approved: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40',
  sent: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40',
  rejected: 'bg-slate-500/15 text-slate-400 ring-slate-500/40',
  blocked: 'bg-red-500/20 text-red-300 ring-red-500/50',
  failed: 'bg-red-500/20 text-red-300 ring-red-500/50',
}

function ActionCard({ action, onChange, onOpenSource }: { action: Action; onChange: (a: Action) => void; onOpenSource: (id: string) => void }) {
  const [draft, setDraft] = useState(action.text)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Text can be edited while the action is waiting, or after it was blocked (to fix the problem).
  const editable = action.status === 'proposed' || action.status === 'blocked'

  const run = async (fn: () => Promise<Action>) => {
    setBusy(true)
    setError(null)
    try {
      const updated = await fn()
      setDraft(updated.text)
      onChange(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // Approve sends the edited text first (PATCH), then approves.
  const approve = () =>
    run(async () => {
      if (draft !== action.text) onChange(await api.editAction(action.id, draft))
      return api.approveAction(action.id)
    })

  return (
    <div className={`rounded-lg border p-3 ${action.status === 'blocked' ? 'border-red-500/60 bg-red-500/5' : 'border-slate-700 bg-slate-900'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-100">{KIND_LABEL[action.kind]}</span>
        <span className="font-mono text-xs text-slate-400">{action.target}</span>
        {action.simulated && (
          <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-xs font-medium text-violet-300 ring-1 ring-violet-500/40">simulated</span>
        )}
        <span className={`ml-auto rounded px-1.5 py-0.5 text-xs font-semibold uppercase ring-1 ${STATUS_STYLE[action.status]}`}>
          {action.status}
        </span>
      </div>
      {action.title && <div className="mt-1 text-sm text-slate-300">{action.title}</div>}

      {action.status === 'blocked' && action.blocked_reason && (
        <div className="mt-2 rounded-md border border-red-500/60 bg-red-500/15 px-3 py-2 text-sm font-medium text-red-200">
          {action.blocked_reason}
        </div>
      )}

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        readOnly={!editable}
        rows={3}
        className={`field-sizing-content mt-2 max-h-80 w-full resize-y rounded-md border px-2 py-1.5 font-mono text-xs leading-relaxed focus:outline-none ${
          editable ? 'border-slate-600 bg-slate-950 text-slate-100 focus:border-sky-500' : 'border-slate-800 bg-slate-950/50 text-slate-400'
        }`}
      />

      {action.cited_ids.length > 0 && (
        <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
          cites <CitationList ids={action.cited_ids} onOpen={onOpenSource} />
        </div>
      )}

      {editable && (
        <div className="mt-3 flex gap-2">
          <button
            disabled={busy}
            onClick={approve}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy ? 'Working...' : draft !== action.text ? 'Save and approve' : 'Approve'}
          </button>
          <button
            disabled={busy}
            onClick={() => run(() => api.rejectAction(action.id))}
            className="rounded-md bg-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-600 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}

      {action.result_url && (
        <a href={action.result_url} target="_blank" rel="noreferrer" className="mt-2 block break-all text-sm text-sky-400 hover:underline">
          {action.result_url}
        </a>
      )}
      {error && <p className="mt-2 text-sm text-red-300">{error}</p>}
    </div>
  )
}

export default function ActionsPanel({ actions, onChange, onOpenSource }: { actions: Action[]; onChange: (a: Action) => void; onOpenSource: (id: string) => void }) {
  return (
    <Panel title="Proposed actions (a human approves)">
      {actions.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing is sent anywhere until you approve it. Proposals appear here.</p>
      ) : (
        <div className="space-y-3">
          {actions.map((a) => (
            <ActionCard key={a.id} action={a} onChange={onChange} onOpenSource={onOpenSource} />
          ))}
        </div>
      )}
    </Panel>
  )
}
