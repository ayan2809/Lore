// Tiny shared pieces: a panel wrapper and a few badges. Kept in one file to stay readable.

import type { ReactNode } from 'react'
import type { AccessLevel } from '../api/types'

export function Panel({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

const ACCESS_STYLES: Record<AccessLevel, string> = {
  public: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40',
  internal: 'bg-sky-500/15 text-sky-300 ring-sky-500/40',
  restricted: 'bg-amber-500/15 text-amber-300 ring-amber-500/40',
  confidential: 'bg-red-500/15 text-red-300 ring-red-500/40',
}

export function AccessBadge({ level }: { level: AccessLevel | null }) {
  if (!level) return null
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ring-1 ${ACCESS_STYLES[level]}`}>{level}</span>
  )
}

/** Yellow warning shown when matching sources exist that this viewer may not read. */
export function RestrictedWarning({ text }: { text: string }) {
  return (
    <div className="flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
      <span className="mt-0.5 h-fit rounded bg-amber-500/20 px-1.5 text-xs font-bold uppercase tracking-wide">restricted</span>
      <span>{text}</span>
    </div>
  )
}
