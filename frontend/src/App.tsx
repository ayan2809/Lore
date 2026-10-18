import { useCallback, useEffect, useState } from 'react'
import { api, isMock } from './api/client'
import type { AlertItem, GraphMode, GraphView, Health, Persona } from './api/types'
import ActionsPanel from './components/ActionsPanel'
import AlertPanel from './components/AlertPanel'
import AskPanel from './components/AskPanel'
import CompareView from './components/CompareView'
import GraphCanvas from './components/GraphCanvas'
import ReportCard from './components/ReportCard'
import RunSummary from './components/RunSummary'
import SourceDrawer from './components/SourceDrawer'
import TopBar from './components/TopBar'
import type { Tab } from './components/TopBar'
import Trail from './components/Trail'
import { Panel } from './components/ui'
import VectorView from './components/VectorView'
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

  // One run per mode: flipping Graph ON/OFF shows that mode's own run (or none), so a Graph ON
  // result is never shown under Graph OFF. "Compare" starts both at once (FIX_LOG F-19).
  const invOn = useInvestigation()
  const invOff = useInvestigation()
  const inv = mode === 'graph' ? invOn : invOff
  const { state } = inv
  const [compare, setCompare] = useState(false)

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
        // a report belongs to one viewer, so start fresh
        invOn.clear()
        invOff.clear()
        setCompare(false)
      } catch (err) {
        setStartupError(err instanceof Error ? err.message : String(err))
      }
    },
    [invOn, invOff],
  )

  const run = () => alertId && inv.start(alertId, mode, replay)
  const startCompare = () => {
    if (!alertId) return
    setCompare(true)
    invOn.start(alertId, 'graph', replay)
    invOff.start(alertId, 'vector', replay)
  }
  const isBusy = (s: typeof state) => s.status === 'starting' || s.status === 'running'
  const busy = isBusy(state)
  const compareBusy = isBusy(invOn.state) || isBusy(invOff.state)
  const alert = alerts.find((a) => a.id === alertId)

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

      {tab === 'investigate' && compare ? (
        <main className="min-h-0 flex-1 overflow-y-auto">
          <CompareView
            alertLabel={alert ? `${alert.name} · ${alert.symptom}` : (alertId ?? '')}
            personaName={persona?.name ?? ''}
            on={{ state: invOn.state, highlights: invOn.highlights, discovered: invOn.discovered }}
            off={{ state: invOff.state, highlights: invOff.highlights, discovered: invOff.discovered }}
            graph={loaded?.graph ?? null}
            loading={graphLoading}
            busy={compareBusy}
            onRunAgain={startCompare}
            onBack={() => setCompare(false)}
            onOpenFull={(m) => {
              setMode(m)
              setCompare(false)
            }}
            onOpenSource={setSourceId}
          />
        </main>
      ) : tab === 'investigate' ? (
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
              onCompare={startCompare}
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
            {mode === 'graph' ? (
              <GraphCanvas
                graph={loaded?.graph ?? null}
                loading={graphLoading}
                discovered={inv.discovered}
                highlights={inv.highlights}
                graphOn
                onOpenSource={setSourceId}
              />
            ) : (
              <VectorView
                graph={loaded?.graph ?? null}
                loading={graphLoading}
                trail={state.trail}
                selectedSeq={state.selectedSeq}
                onOpenSource={setSourceId}
              />
            )}
          </div>

          <div className="space-y-3 lg:overflow-y-auto">
            <ReportCard report={state.report} investigationId={state.investigationId} running={busy} onOpenSource={setSourceId} />
            {mode === 'vector' && (
              <Panel title="Not available with Graph OFF">
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
                  <li>Severity: it comes from the blast radius</li>
                  <li>The evidence path from the alert to the PR</li>
                  <li>Who to page: owners come from the graph</li>
                  <li>Recent changes in time order, per service</li>
                </ul>
              </Panel>
            )}
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
