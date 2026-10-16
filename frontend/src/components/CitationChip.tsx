import { labelFromId, nodeColor } from '../lib/format'

/** A clickable source id. Clicking opens the SourceDrawer. */
export default function CitationChip({ id, onOpen }: { id: string; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(id)}
      title={`Open ${id}`}
      className="inline-flex items-center gap-1.5 rounded-md bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-slate-200 ring-1 ring-slate-700 transition hover:bg-slate-700 hover:ring-sky-500"
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: nodeColor(labelFromId(id)) }} />
      {id}
    </button>
  )
}

export function CitationList({ ids, onOpen }: { ids: string[]; onOpen: (id: string) => void }) {
  if (ids.length === 0) return null
  return (
    <span className="inline-flex flex-wrap gap-1">
      {ids.map((id) => (
        <CitationChip key={id} id={id} onOpen={onOpen} />
      ))}
    </span>
  )
}
