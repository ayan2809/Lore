import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type { ForceGraphMethods, LinkObject, NodeObject } from 'react-force-graph-2d'
import type { EdgeRef, GraphView } from '../api/types'
import { pairKey } from '../hooks/investigationState'
import type { Highlights } from '../hooks/investigationState'
import { isSourceLabel, labelFromId, nodeColor, NODE_COLORS } from '../lib/format'
import { AccessBadge } from './ui'

// react-force-graph lets us attach any fields to nodes; these are ours.
type GNode = NodeObject
type GLink = LinkObject

interface Props {
  graph: GraphView | null
  loading: boolean
  /** Nodes/edges tools touched that the graph view may not contain; we add them. */
  discovered: { nodeIds: string[]; edges: EdgeRef[] }
  highlights: Highlights
  graphOn: boolean
  onOpenSource: (id: string) => void
}

const LEGEND = ['Service', 'Person', 'Team', 'PR', 'Deploy', 'Alert', 'Decision', 'Incident', 'Thread']

// Camera and motion timings (the design: "How the graph moves between steps").
const CAMERA_MS = 1200 // one glide: pan and zoom together
const STEP_GAP_MS = 1400 // at most one camera move per this long; quicker steps skip to the newest
const FADE_MS = 400 // a node added during a run fades in
const ZOOM_MIN = 1 // while following a run, zoom stays between these multiples of the whole-graph view
const ZOOM_MAX = 2.6

// A link's endpoints are strings at first and become node objects once the simulation runs.
const endId = (end: unknown): string => (typeof end === 'object' && end !== null ? String((end as GNode).id) : String(end))

/** Track the size of a container so the canvas fills it. */
function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 800, height: 600 })
  useEffect(() => {
    if (!ref.current) return
    const obs = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width: Math.max(200, width), height: Math.max(200, height) })
    })
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return [ref, size] as const
}

export default function GraphCanvas({ graph, loading, discovered, highlights, graphOn, onOpenSource }: Props) {
  const [wrap, size] = useSize<HTMLDivElement>()
  const fg = useRef<ForceGraphMethods | undefined>(undefined)
  const [picked, setPicked] = useState<GNode | null>(null)
  const settled = useRef(false) // the first layout has finished; from then on nodes are pinned
  const baseZoom = useRef<number | null>(null) // zoom of the whole-graph view
  const lastMove = useRef(0)

  // Keep node objects between renders: the simulation stores x/y on them, so reusing them
  // stops the layout from jumping each time a tool result adds a node.
  const [nodeCache] = useState(() => new Map<string, GNode>())
  // The last graphData we handed over, and what it contained. Every trail event rebuilds
  // `discovered`, but a new graphData object restarts the physics and makes every node twitch,
  // so we only hand over a new one when a node or link was actually added (FIX_LOG F-18).
  const lastData = useRef<{ key: string; data: { nodes: GNode[]; links: GLink[] } } | null>(null)

  // A different persona or alert: let the whole layout settle again.
  useEffect(() => {
    settled.current = false
    baseZoom.current = null
    for (const n of nodeCache.values()) {
      n.fx = undefined
      n.fy = undefined
    }
  }, [graph, nodeCache])

  const data = useMemo(() => {
    const cache = nodeCache
    const nodes = new Map<string, GNode>()
    const fresh: GNode[] = []
    const put = (id: string, label: string, name: string, accessLevel: string | null, tier?: number) => {
      let node = cache.get(id)
      if (!node) {
        node = { id }
        fresh.push(node)
        cache.set(id, node)
      }
      Object.assign(node, { label, name, accessLevel, tier })
      nodes.set(id, node)
    }
    for (const n of graph?.nodes ?? []) put(n.id, n.label, n.name, n.access_level, n.props.tier as number | undefined)
    // Tool results can mention nodes outside the loaded neighbourhood: add them, guessing the label from the id.
    for (const id of discovered.nodeIds) if (!nodes.has(id)) put(id, labelFromId(id), id, null)

    const seen = new Set<string>()
    const links: { source: string; target: string; type: string }[] = []
    for (const e of [...(graph?.links ?? []), ...discovered.edges]) {
      const key = `${e.source}|${e.target}|${e.type}`
      if (seen.has(key) || !nodes.has(e.source) || !nodes.has(e.target)) continue
      seen.add(key)
      links.push({ source: e.source, target: e.target, type: e.type })
    }

    const key = `${[...nodes.keys()].join(',')}#${[...seen].join(',')}`
    if (lastData.current?.key === key) return lastData.current.data

    // Mid-run, a new node starts beside a node it links to (not in the middle of the canvas)
    // and fades in; the pinned layout around it stays still.
    if (settled.current) {
      const now = performance.now()
      // A node with no link to a placed node goes near what the run has touched so far,
      // so the camera never flies off to an empty corner for it.
      const touched = discovered.nodeIds.map((id) => cache.get(id)).filter((n) => n && !fresh.includes(n) && n.x !== undefined) as GNode[]
      const centre = touched.length
        ? { x: touched.reduce((s, n) => s + (n.x ?? 0), 0) / touched.length, y: touched.reduce((s, n) => s + (n.y ?? 0), 0) / touched.length }
        : null
      for (const node of fresh) {
        const id = String(node.id)
        const link = links.find((l) => (l.source === id && cache.get(l.target)?.x !== undefined) || (l.target === id && cache.get(l.source)?.x !== undefined))
        const anchor = (link && cache.get(link.source === id ? link.target : link.source)) ?? centre
        if (anchor?.x !== undefined && anchor.y !== undefined) {
          const angle = Math.random() * 2 * Math.PI
          node.x = anchor.x + 30 * Math.cos(angle)
          node.y = anchor.y + 30 * Math.sin(angle)
        }
        node.bornAt = now
      }
    }

    const result = { nodes: [...nodes.values()], links }
    lastData.current = { key, data: result }
    return result
  }, [graph, discovered, nodeCache])

  // Spread nodes out a bit more than the default.
  useEffect(() => {
    fg.current?.d3Force('charge')?.strength(-140)
  }, [])

  /** Where to put the camera to show the box around these nodes, with `pad` screen px around it. */
  const frame = (filter: (n: GNode) => boolean, pad: number) => {
    const box = fg.current?.getGraphBbox(filter)
    if (!box) return null
    const w = Math.max(box.x[1] - box.x[0], 1)
    const h = Math.max(box.y[1] - box.y[0], 1)
    const k = Math.min((size.width - 2 * pad) / w, (size.height - 2 * pad) / h)
    return { x: (box.x[0] + box.x[1]) / 2, y: (box.y[0] + box.y[1]) / 2, k: Math.max(k, 0.05) }
  }

  const glide = (to: { x: number; y: number; k: number }) => {
    lastMove.current = performance.now()
    fg.current?.centerAt(to.x, to.y, CAMERA_MS)
    fg.current?.zoom(to.k, CAMERA_MS)
  }

  const fitAll = () => {
    const all = frame(() => true, 50)
    if (!all) return
    baseZoom.current = all.k
    glide(all)
  }

  // Follow the run: glide to the lit nodes of the newest step (or the evidence path at the end).
  // The ref avoids re-running when unrelated trail items arrive.
  const latest = useRef(highlights)
  useEffect(() => {
    latest.current = highlights
  })
  useEffect(() => {
    if (!highlights.focus) return
    const wait = Math.max(250, lastMove.current + STEP_GAP_MS - performance.now())
    const t = setTimeout(() => {
      const lit = latest.current.activeNodes
      const to = frame((n) => lit.has(String(n.id)), 110)
      if (!to) return
      const base = baseZoom.current
      if (base) to.k = Math.min(Math.max(to.k, base * ZOOM_MIN), base * ZOOM_MAX)
      glide(to)
    }, wait)
    return () => clearTimeout(t)
    // Only move when what is in focus changes (not on every new trail item).
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [highlights.focus])

  const anyHighlight = highlights.activeNodes.size + highlights.seenNodes.size > 0

  const radius = (n: GNode) => (n.label === 'Service' ? 8 - (n.tier ?? 3) : n.label === 'Alert' ? 7 : 4.5)

  const paintNode = (n: GNode, ctx: CanvasRenderingContext2D, scale: number) => {
    const id = String(n.id)
    const active = highlights.activeNodes.has(id)
    const seen = highlights.seenNodes.has(id)
    const color = nodeColor(n.label)
    const r = radius(n)
    const x = n.x ?? 0
    const y = n.y ?? 0
    const fade = n.bornAt ? Math.min(1, (performance.now() - n.bornAt) / FADE_MS) : 1

    ctx.save()
    ctx.globalAlpha = (anyHighlight && !active && !seen ? 0.28 : 1) * fade

    if (active) {
      // glow + a slow, soft pulse ring
      ctx.shadowColor = color
      ctx.shadowBlur = 18
      const pulse = 1 + 0.25 * Math.sin((performance.now() / 1600) * 2 * Math.PI)
      ctx.beginPath()
      ctx.arc(x, y, (r + 4) * pulse, 0, 2 * Math.PI)
      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.arc(x, y, active ? r + 1.5 : r, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
    ctx.shadowBlur = 0
    if (seen && !active) {
      ctx.beginPath()
      ctx.arc(x, y, r + 2.5, 0, 2 * Math.PI)
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.55 * fade
      ctx.lineWidth = 1.2
      ctx.stroke()
    }
    ctx.restore()

    // Labels: always for highlighted nodes, others only once zoomed in.
    if (active || seen || scale > 1.8 || picked?.id === n.id) {
      const text = String(n.name)
      const size = (active ? 13 : 11) / scale
      ctx.save()
      ctx.globalAlpha = fade
      ctx.font = `${active ? 600 : 400} ${size}px system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const w = ctx.measureText(text).width
      const ty = y + r + 3 / scale
      if (active) {
        ctx.fillStyle = 'rgba(2,6,23,0.8)'
        ctx.fillRect(x - w / 2 - 2 / scale, ty - 1 / scale, w + 4 / scale, size + 2 / scale)
      }
      ctx.fillStyle = active ? '#f8fafc' : seen ? '#cbd5e1' : '#94a3b8'
      ctx.fillText(text, x, ty)
      ctx.restore()
    }
  }

  const linkState = (l: GLink) => {
    const k = pairKey(endId(l.source), endId(l.target))
    return highlights.activeEdges.has(k) ? 'active' : highlights.seenEdges.has(k) ? 'seen' : 'idle'
  }

  return (
    <div ref={wrap} className="relative h-full min-h-[24rem] w-full overflow-hidden rounded-xl border border-slate-800 bg-[#050b1a]">
      <ForceGraph2D
        ref={fg}
        width={size.width}
        height={size.height}
        graphData={data}
        backgroundColor="#050b1a"
        autoPauseRedraw={false} // we animate pulses and particles every frame
        cooldownTicks={140}
        nodeCanvasObjectMode={() => 'replace'}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(n, color, ctx) => {
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(n.x ?? 0, n.y ?? 0, radius(n) + 3, 0, 2 * Math.PI)
          ctx.fill()
        }}
        nodeLabel={(n) => `${n.label}: ${n.id}`}
        linkColor={(l) => {
          const s = linkState(l)
          return s === 'active' ? '#38bdf8' : s === 'seen' ? 'rgba(56,189,248,0.5)' : 'rgba(100,116,139,0.28)'
        }}
        linkWidth={(l) => ({ active: 2.6, seen: 1.6, idle: 0.6 })[linkState(l)]}
        linkDirectionalParticles={(l) => (linkState(l) === 'active' ? 4 : 0)}
        linkDirectionalParticleSpeed={0.012}
        linkDirectionalParticleWidth={3.2}
        linkDirectionalParticleColor={() => '#e0f2fe'}
        linkDirectionalArrowLength={(l) => (linkState(l) === 'idle' ? 0 : 4)}
        linkDirectionalArrowRelPos={0.92}
        linkDirectionalArrowColor={() => '#38bdf8'}
        onNodeClick={(n) => setPicked(n)}
        onBackgroundClick={() => setPicked(null)}
        onNodeDragEnd={(n) => {
          // keep a dragged node where it was dropped
          n.fx = n.x
          n.fy = n.y
        }}
        onEngineStop={() => {
          // Pin every node where it settled: later tool results only add nodes, never move these.
          for (const n of data.nodes) {
            n.fx = n.x
            n.fy = n.y
          }
          if (!settled.current) {
            settled.current = true
            // Fit the whole graph once, unless a run is already following highlighted nodes.
            const all = frame(() => true, 50)
            if (all) baseZoom.current = all.k
            if (all && latest.current.activeNodes.size === 0) glide(all)
          }
        }}
      />

      {/* legend */}
      <div className="pointer-events-none absolute left-3 top-3 flex max-w-[16rem] flex-wrap gap-x-3 gap-y-1 rounded-lg bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
        {LEGEND.map((l) => (
          <span key={l} className="flex items-center gap-1">
            <span className="size-2 rounded-full" style={{ backgroundColor: NODE_COLORS[l] }} />
            {l}
          </span>
        ))}
      </div>

      <div className="pointer-events-none absolute right-3 top-3 flex flex-col items-end gap-1.5 text-xs">
        {!graphOn && (
          <span className="rounded bg-slate-800/90 px-2 py-1 font-semibold text-slate-300 ring-1 ring-slate-600">
            Graph OFF: vector-only baseline (no graph walking)
          </span>
        )}
        <div className="flex items-center gap-2">
          {anyHighlight && (
            <span className="rounded bg-slate-950/70 px-2 py-1 text-slate-300">
              {highlights.activeNodes.size} lit · {highlights.seenNodes.size} visited earlier
            </span>
          )}
          {graph && (
            <button
              onClick={fitAll}
              className="pointer-events-auto rounded border border-slate-700 bg-slate-900/90 px-2.5 py-1 text-slate-300 hover:border-slate-500 hover:text-white"
            >
              Fit all
            </button>
          )}
        </div>
      </div>

      {loading && <div className="absolute inset-0 grid place-items-center text-slate-400">Loading graph...</div>}
      {!loading && !graph && (
        <div className="absolute inset-0 grid place-items-center text-slate-500">Graph unavailable</div>
      )}

      {picked && (
        <div className="absolute bottom-3 left-3 max-w-sm rounded-lg border border-slate-700 bg-slate-900/95 p-3 text-sm shadow-xl">
          <div className="flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ backgroundColor: nodeColor(picked.label) }} />
            <span className="font-semibold text-slate-100">{picked.label}</span>
            <AccessBadge level={picked.accessLevel} />
            <button onClick={() => setPicked(null)} className="ml-auto text-xs text-slate-500 hover:text-slate-300">
              close
            </button>
          </div>
          <div className="mt-1 text-slate-300">{picked.name}</div>
          <div className="font-mono text-xs text-slate-500">{String(picked.id)}</div>
          {isSourceLabel(picked.label) && (
            <button onClick={() => onOpenSource(String(picked.id))} className="mt-2 text-xs text-sky-400 hover:text-sky-300">
              Open source
            </button>
          )}
        </div>
      )}
    </div>
  )
}
