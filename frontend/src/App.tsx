import { useCallback, useEffect, useState } from 'react'
import { api, isMock } from './api/client'
import type { AlertItem, GraphMode, GraphView, Health, Persona } from './api/types'
import ActionsPanel from './components/ActionsPanel'
import AlertPanel from './components/AlertPanel'
import AskPanel from './components/AskPanel'
import GraphCanvas from './components/GraphCanvas'
import ReportCard from './components/ReportCard'
import RunSummary from './components/RunSummary'
import SourceDrawer from './components/SourceDrawer'
import TopBar from './components/TopBar'
import type { Tab } from './components/TopBar'
import Trail from './components/Trail'
import { useInvestigation } from './hooks/useInvestigation'

export default function App() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [persona, setPersona] = useState<Persona | null>(null)
  const [mode, setMode] = useState<GraphMode>('graph')
  const [tab, setTab] = useState<Tab>('investigate')
  const [health, setHealth] = useState<Health | null>(null)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [alertId, setAlertId] = useState<string | null>(null)
  const [replay, setReplay] = useState(false)
  // The loaded graph remembers which persona + centre it was loaded for ("key"), so we can tell when it is stale.
  const [loaded, setLoaded] = useState<{ key: string; graph: GraphView | null } | null>(null)
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [startupError, setStartupError] = useState<string | null>(null)

  const inv = useInvestigation()
  const { state } = inv

  // ---- startup: personas, the current session (default Arjun), alerts
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [list, alertList] = await Promise.all([api.personas(), api.alerts()])
        // No session cookie yet? Sign in as Arjun, the on-call engineer from the demo.
        const session = await api.getSession().catch(() => api.setSession('arjun'))
        if (cancelled) return
        setPersonas(list)
        setPersona(session.persona)
        setAlerts(alertList)
        setAlertId(alertList[0]?.id ?? null)
      } catch (err) {
        if (!cancelled) setStartupError(err instanceof Error ? err.message : String(err))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // ---- health dots, refreshed every 15 seconds
  useEffect(() => {
    const check = () => api.health().then(setHealth).catch(() => setHealth(null))
    check()
    const timer = setInterval(check, 15000)
    return () => clearInterval(timer)
  }, [])

  // ---- the graph view depends on who is logged in (permission-filtered by the server)
  const centre = alerts.find((a) => a.id === alertId)?.service ?? 'svc:checkout'
  const graphKey = `${persona?.id}|${centre}`
  useEffect(() => {
    if (!persona) return
    let cancelled = false
    api
      .graph({ center: centre, hops: 2, limit: 200 })
      .then((graph) => !cancelled && setLoaded({ key: graphKey, graph }))
      .catch(() => !cancelled && setLoaded({ key: graphKey, graph: null }))
    return () => {
      cancelled = true
    }
  }, [persona, centre, graphKey])
  const graphLoading = loaded?.key !== graphKey

  const switchPersona = useCallback(
    async (id: string) => {
      try {
        const { persona: p } = await api.setSession(id)
        setPersona(p)
        inv.clear() // a report belongs to one viewer, so start fresh
      } catch (err) {
        setStartupError(err instanceof Error ? err.message : String(err))
      }
    },
    [inv],
  )

  const run = () => alertId && inv.start(alertId, mode, replay)
  const busy = state.status === 'starting' || state.status === 'running'

  return (
    <div className="flex h-screen flex-col">
      <TopBar
        personas={personas}
        persona={persona}
        onPersona={switchPersona}
        mode={mode}
        onMode={setMode}
        health={health}
        tab={tab}
        onTab={setTab}
        mock={isMock}
      />

      {startupError && (
        <div className="border-b border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-200">
          Cannot reach the backend: {startupError}. Start it, or run with VITE_MOCK=1 (see frontend/README.md).
        </div>
      )}
      {state.error && (
        <div className="border-b border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-200">
          Investigation failed: {state.error}
        </div>
      )}

      {tab === 'investigate' ? (
        <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-y-auto p-3 lg:grid-cols-[19rem_minmax(0,1fr)_22rem] lg:overflow-hidden xl:grid-cols-[24rem_minmax(0,1fr)_29rem]">
          <div className="flex min-h-0 flex-col gap-3">
            <AlertPanel
              alerts={alerts}
              selectedId={alertId}
              onSelect={setAlertId}
              status={state.status}
              personaName={persona?.name ?? ''}
              replay={replay}
              onReplay={setReplay}
              onRun={run}
            />
            <Trail
              trail={state.trail}
              status={state.status}
              activeSeq={inv.highlights.activeSeq}
              selectedSeq={state.selectedSeq}
              onSelect={inv.selectStep}
              onOpenSource={setSourceId}
            />
          </div>

          <div className="h-[28rem] lg:h-auto">
            <GraphCanvas
              graph={loaded?.graph ?? null}
              loading={graphLoading}
              discovered={inv.discovered}
              highlights={inv.highlights}
              graphOn={mode === 'graph'}
              onOpenSource={setSourceId}
            />
          </div>

          <div className="space-y-3 lg:overflow-y-auto">
            <ReportCard report={state.report} investigationId={state.investigationId} running={busy} onOpenSource={setSourceId} />
            <ActionsPanel actions={state.actions} onChange={inv.updateAction} onOpenSource={setSourceId} />
            <RunSummary summary={state.summary} mode={state.mode} />
          </div>
        </main>
      ) : (
        <main className="min-h-0 flex-1 overflow-y-auto">
          <AskPanel key={persona?.id} mode={mode} personaName={persona?.name ?? ''} onOpenSource={setSourceId} />
        </main>
      )}

      <SourceDrawer id={sourceId} onClose={() => setSourceId(null)} />
    </div>
  )
}
