// HTTP client for the FastAPI backend (docs/PROJECT_CONTEXT.md section 6).
// At the bottom, `api` picks the real client or the mock: the ONLY place that decides.

import { mockApi } from './mock'
import { EVENT_TYPES } from './types'
import type { Api, EventType, StepEvent } from './types'

const BASE = (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** JSON fetch. `credentials: 'include'` sends the lore_session cookie (needed cross-origin). */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? body.message ?? detail // FastAPI errors use `detail`
    } catch {
      /* body was not JSON; keep statusText */
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (await res.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

/** Safe upper bound for browser auto-reconnects before we give up and show an error. */
const MAX_STREAM_ERRORS = 5

const realApi: Api = {
  health: () => request('/health'),
  personas: () => request('/personas'),
  getSession: () => request('/session'),
  setSession: (persona) => post('/session', { persona }),
  alerts: () => request('/alerts'),

  graph: ({ center, hops, limit } = {}) => {
    const q = new URLSearchParams()
    if (center) q.set('center', center)
    if (hops) q.set('hops', String(hops))
    if (limit) q.set('limit', String(limit))
    return request(`/graph?${q}`)
  },

  startInvestigation: (req) => post('/investigations', req),
  getInvestigation: (id) => request(`/investigations/${encodeURIComponent(id)}`),
  sendFeedback: (id, body) => post(`/investigations/${encodeURIComponent(id)}/feedback`, body),

  ask: (body) => post('/ask', body),

  editAction: (id, text) =>
    request(`/actions/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ text }) }),
  approveAction: (id) => post(`/actions/${encodeURIComponent(id)}/approve`),
  rejectAction: (id) => post(`/actions/${encodeURIComponent(id)}/reject`),

  getSource: (id) => request(`/sources/${encodeURIComponent(id)}`),

  // SSE: the server sets `event:` = StepEvent.type, so we need one listener per type.
  subscribeToInvestigation: (id, onEvent, onClose) => {
    const es = new EventSource(`${BASE}/api/investigations/${encodeURIComponent(id)}/events`, {
      withCredentials: true,
    })
    let errors = 0
    let closed = false

    const finish = (error?: Error) => {
      if (closed) return
      closed = true
      es.close()
      onClose?.(error)
    }

    for (const type of EVENT_TYPES) {
      es.addEventListener(type, (e) => {
        errors = 0
        const event = JSON.parse((e as MessageEvent<string>).data) as StepEvent
        onEvent(event)
        if ((type as EventType) === 'done') finish() // server is finished; stop auto-reconnect
      })
    }

    es.onerror = () => {
      // EventSource reconnects by itself (readyState CONNECTING). If the browser gave up
      // (CLOSED) or it keeps failing, report it. The hook drops duplicate events by `seq`.
      errors += 1
      if (es.readyState === EventSource.CLOSED || errors >= MAX_STREAM_ERRORS) {
        finish(new Error('Lost connection to the event stream'))
      }
    }

    return () => {
      closed = true
      es.close()
    }
  },
}

// One switch: `VITE_MOCK=1` runs the whole UI against fixtures in the browser.
export const api: Api = import.meta.env.VITE_MOCK === '1' ? mockApi : realApi

export const isMock = import.meta.env.VITE_MOCK === '1'
