import { useState } from 'react'
import { api } from '../api/client'
import type { Claim, Report, Severity } from '../api/types'
import { displayName, restrictedMessage } from '../lib/format'
import CitationChip, { CitationList } from './CitationChip'
import { Panel, RestrictedWarning } from './ui'

const SEVERITY_STYLES: Record<Severity, string> = {
  P1: 'bg-red-600 text-white',
  P2: 'bg-orange-500 text-white',
  P3: 'bg-yellow-500 text-slate-900',
}

function ClaimList({ claims, onOpen }: { claims: Claim[]; onOpen: (id: string) => void }) {
  return (
    <ul className="space-y-2.5">
      {claims.map((c, i) => (
        <li key={i} className="text-sm leading-relaxed text-slate-200">
          {c.text} <CitationList ids={c.citations} onOpen={onOpen} />
        </li>
      ))}
    </ul>
  )
}

function Person({ label, ids }: { label: string; ids: string[] }) {
  if (ids.length === 0) return null
  return (
    <div className="rounded-lg bg-slate-800/70 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="font-medium text-slate-100">{ids.map(displayName).join(', ')}</div>
    </div>
  )
}

interface Props {
  report: Report | null
  investigationId: string | null
  running: boolean
  onOpenSource: (id: string) => void
}

export default function ReportCard({ report, investigationId, running, onOpenSource }: Props) {
  const [feedback, setFeedback] = useState<string | null>(null)

  if (!report) {
    return (
      <Panel title="Root-cause report">
        <p className="text-sm text-slate-500">
          {running ? 'The report appears when the agents finish.' : 'Run the incident to get a cited root-cause report.'}
        </p>
      </Panel>
    )
  }

  const sendFeedback = async (confirmed: boolean) => {
    if (!investigationId) return
    try {
      const r = await api.sendFeedback(investigationId, { confirmed })
      setFeedback(
        confirmed ? (r.playbook_id ? `Thanks. Saved playbook ${r.playbook_id} for next time.` : 'Thanks, confirmed.') : 'Noted. Not saved as a playbook.',
      )
    } catch (err) {
      setFeedback(`Could not send feedback: ${err instanceof Error ? err.message : err}`)
    }
  }

  return (
    <Panel
      title="Root-cause report"
      right={
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">confidence {Math.round(report.confidence * 100)}%</span>
          {report.severity && (
            <span className={`rounded-md px-2 py-0.5 text-sm font-bold ${SEVERITY_STYLES[report.severity]}`}>{report.severity}</span>
          )}
        </div>
      }
    >
      <p className="text-base font-medium leading-snug text-white">{report.summary}</p>

      {report.restricted_matches > 0 && (
        <div className="mt-3">
          <RestrictedWarning text={restrictedMessage(report.restricted_matches, report.restricted_owner_hint)} />
        </div>
      )}

      {report.root_cause && (
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-400">Root cause</span>
          <CitationChip id={report.root_cause} onOpen={onOpenSource} />
        </div>
      )}

      {report.evidence_path.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-slate-500">
          {report.evidence_path.map((id, i) => (
            <span key={id} className="flex items-center gap-1">
              {i > 0 && <span>›</span>}
              <span className="font-mono text-slate-300">{id}</span>
            </span>
          ))}
        </div>
      )}

      {report.rejected_suspects.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">Ruled out</h3>
          <ClaimList claims={report.rejected_suspects} onOpen={onOpenSource} />
        </div>
      )}

      {report.claims.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence (every claim cites a source)</h3>
          <ClaimList claims={report.claims} onOpen={onOpenSource} />
        </div>
      )}

      {(report.people.page || report.people.consult.length > 0 || report.people.notify.length > 0) && (
        <div className="mt-4">
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">Who to contact</h3>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <Person label="Page" ids={report.people.page ? [report.people.page] : []} />
            <Person label="Consult" ids={report.people.consult} />
            <Person label="Notify" ids={report.people.notify} />
          </div>
        </div>
      )}

      {report.dropped_claims.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950/50 p-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Dropped by the citation check ({report.dropped_claims.length})
          </h3>
          {report.dropped_claims.map((c, i) => (
            <p key={i} className="text-sm text-slate-500 line-through">{c.text}</p>
          ))}
          <p className="mt-1 text-xs text-slate-500">The model said this without citing a source it had actually seen, so it was removed.</p>
        </div>
      )}

      <div className="mt-4 flex items-center gap-2 border-t border-slate-800 pt-3 text-sm">
        {feedback ? (
          <span className="text-slate-300">{feedback}</span>
        ) : (
          <>
            <span className="text-slate-400">Was this the real cause?</span>
            <button onClick={() => sendFeedback(true)} className="rounded-md bg-emerald-600/80 px-2.5 py-1 font-medium text-white hover:bg-emerald-500">
              Yes, remember it
            </button>
            <button onClick={() => sendFeedback(false)} className="rounded-md bg-slate-700 px-2.5 py-1 text-slate-200 hover:bg-slate-600">
              No
            </button>
          </>
        )}
      </div>
    </Panel>
  )
}
