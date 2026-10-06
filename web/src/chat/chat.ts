// Pure logic of the chat view (decision 0031): request building, history, error text. No React here, so it is unit tested.

export type Style = 'summary' | 'quotes'

export interface Quote {
  review_id: string
  date: string
  quote: string
}
export interface Standing {
  words: string
  n_mentions: number
}
export interface Place {
  id: number
  name: string | null
  kind: string
  area: string
  relevant: boolean
  summary: string
  quotes: Quote[]
  standing: Record<string, Standing>
}
/** What the server wants back for the next message: the standalone question, what was searched, and the places shown. */
export interface TurnMemo {
  question: string
  searched_for: string
  places: string[]
}
export interface ChatResponse {
  status: string
  banner: string
  message: string
  question: string
  followup: boolean
  searched_for: string
  caveat: string
  notice: string
  alphabetical: boolean
  in_scope: boolean
  places: Place[]
  dropped: { quotes: number; places: number }
  models: Record<string, string | null>
  turn: TurnMemo
}
export interface ChatTurn {
  id: number
  message: string
  style: Style
  state: 'pending' | 'done' | 'error'
  response?: ChatResponse
  error?: string
  startedAt: number
}

export const MAX_QUESTION = 500 // the server's limit
export const MAX_HISTORY_SENT = 6
export const ENDPOINT = '/api/tablemap/chat'

export const SUGGESTIONS = [
  'Quiet cafes in Rittenhouse with good service',
  'Where can I sit outside for a drink?',
  'Cheap eats near the subway',
  'Best bar in Roxborough',
]

export const canSend = (text: string): boolean => text.trim().length > 0 && text.trim().length <= MAX_QUESTION

/** The earlier turns the server needs: only the ones that completed, as the server described them, oldest first, at most MAX_HISTORY_SENT. */
export function buildHistory(turns: ChatTurn[]): TurnMemo[] {
  return turns
    .filter((t) => t.state === 'done' && t.response)
    .map((t) => (t.response as ChatResponse).turn)
    .slice(-MAX_HISTORY_SENT)
}

export function buildRequest(message: string, style: Style, turns: ChatTurn[]) {
  return { question: message.trim(), style, history: buildHistory(turns) }
}

/** Plain-language text for a failed request, from the status and the server's `detail` when it sent one. */
export function errorText(status: number | null, detail?: string): string {
  if (status === null) return 'Cannot reach the API. Is it running (uvicorn on port 8000)?'
  if (status === 404) return 'The chat endpoints are off. Restart the API with: STREETWALKER_TABLEMAP=1 .venv/bin/uvicorn streetwalker.api:app --port 8000'
  // Our server always sends a detail with a 502 or 503. A gateway error with none (a dev proxy whose target is down) means the API is unreachable.
  if (status === 502 || status === 503 || status === 504) return detail || errorText(null)
  if (status === 422) return 'The question or the conversation was not accepted (too long, or malformed).'
  return `The request failed (${status}).`
}

export function elapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

/** The places the answer stands behind, and the ones the search returned but the check did not accept. */
export function splitPlaces(places: Place[]): { shown: Place[]; other: Place[] } {
  return { shown: places.filter((p) => p.relevant), other: places.filter((p) => !p.relevant) }
}

export const areaLabel = (area: string): string => area.replace(/_/g, ' ')
export const monthOf = (date: string): string => date.slice(0, 7)
