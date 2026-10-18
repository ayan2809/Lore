// Wires the pure reducer (investigationState.ts) to the API: start a run, listen to SSE,
// and expose the state plus a few actions to the components.

import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react'
import { api } from '../api/client'
import type { Action, GraphMode } from '../api/types'
import { computeHighlights, discoveredFromTrail, initialState, reduce } from './investigationState'

export function useInvestigation() {
  const [state, dispatch] = useReducer(reduce, initialState)
  const unsubscribe = useRef<(() => void) | null>(null)
  const runToken = useRef(0) // lets us ignore callbacks from an older run

  const stop = useCallback(() => {
    unsubscribe.current?.()
    unsubscribe.current = null
  }, [])

  useEffect(() => stop, [stop]) // close the stream when the app unmounts

  const start = useCallback(
    async (alertId: string, mode: GraphMode, replay: boolean) => {
      stop()
      const token = ++runToken.current
      dispatch({ t: 'starting', alertId, mode, replay })
      try {
        const started = await api.startInvestigation({ alert_id: alertId, mode, replay })
        const investigation_id = started.investigation_id
        if (token !== runToken.current) return
        const notice =
          started.replay_reason === 'daily_live_limit'
            ? "Today's live runs for this public demo are used up, so this is a recorded run of the same incident."
            : undefined
        dispatch({ t: 'started', investigationId: investigation_id, notice })

        unsubscribe.current = api.subscribeToInvestigation(
          investigation_id,
          (event) => {
            if (token === runToken.current) dispatch({ t: 'event', event })
          },
          (error) => {
            if (token !== runToken.current) return
            if (error) dispatch({ t: 'failed', message: error.message })
            // Either way, ask the server for the final state to fill any gaps.
            api
              .getInvestigation(investigation_id)
              .then((snapshot) => token === runToken.current && dispatch({ t: 'snapshot', snapshot }))
              .catch(() => {})
          },
        )
      } catch (err) {
        if (token === runToken.current) {
          dispatch({ t: 'failed', message: err instanceof Error ? err.message : String(err) })
        }
      }
    },
    [stop],
  )

  const clear = useCallback(() => {
    stop()
    runToken.current++
    dispatch({ t: 'clear' })
  }, [stop])

  const selectStep = useCallback((seq: number | null) => dispatch({ t: 'select', seq }), [])
  const updateAction = useCallback((action: Action) => dispatch({ t: 'action', action }), [])

  // Derived data for the graph canvas
  const highlights = useMemo(() => computeHighlights(state.trail, state.selectedSeq), [state.trail, state.selectedSeq])
  const discovered = useMemo(() => discoveredFromTrail(state.trail), [state.trail])

  return { state, highlights, discovered, start, clear, selectStep, updateAction }
}
