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
  lowest_first?: boolean
  in_scope: boolean
  places: Place[]
  dropped: { quotes: number; places: number }
  models: Record<string, string | null>
  turn: TurnMemo
}
/** What the server has said so far about an answer it is still working on (decision 0032). */
export interface Progress {
  text: string
  question?: string
  followup?: boolean
  searched_for?: string
  places?: string[]
  done?: number
  total?: number
}
export interface ChatTurn {
  id: number
  message: string
  style: Style
  state: 'pending' | 'done' | 'error'
  response?: ChatResponse
  error?: string
  startedAt: number
  progress?: Progress
}

/** One line of the server's stream (newline-delimited JSON). */
export type StreamEvent =
  | { event: 'stage'; stage: string; text?: string; question?: string; followup?: boolean; searched_for?: string; places?: string[]; done?: number; total?: number }
  | { event: 'answer'; data: ChatResponse }
  | { event: 'error'; status: number; detail?: string }
  | { event: 'cancelled' }

export const MAX_QUESTION = 500 // the server's limit
export const MAX_HISTORY_SENT = 6
export const ENDPOINT = '/api/tablemap/chat/stream'
export const STORAGE_KEY = 'streetwalker.chat.v1'
export const MAX_SAVED_TURNS = 20

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

export function buildRequest(message: string, style: Style, turns: ChatTurn[], strict = false) {
  return { question: message.trim(), style, strict, history: buildHistory(turns) }
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

/** Split what has arrived so far into complete events and the unfinished tail. Blank lines (the server's keep-alive) and lines that are not
 *  JSON are skipped, so a half-sent line is never mistaken for an event. */
export function parseStream(buffer: string): { events: StreamEvent[]; rest: string } {
  const parts = buffer.split('\n')
  const rest = parts.pop() ?? ''
  const events: StreamEvent[] = []
  for (const line of parts) {
    if (!line.trim()) continue
    try {
      const ev = JSON.parse(line) as StreamEvent
      if (ev && typeof ev === 'object' && 'event' in ev) events.push(ev)
    } catch {
      /* not an event */
    }
  }
  return { events, rest }
}

/** What to show while waiting: each stage event replaces the text and adds what it knows (what was searched, the places found, how far the check is). */
export function applyStage(prev: Progress | undefined, ev: Extract<StreamEvent, { event: 'stage' }>): Progress {
  const next: Progress = { ...prev, text: ev.text ?? prev?.text ?? '' }
  if (ev.question !== undefined) next.question = ev.question
  if (ev.followup !== undefined) next.followup = ev.followup
  if (ev.searched_for) next.searched_for = ev.searched_for
  if (ev.places) next.places = ev.places
  if (ev.stage === 'check' && ev.total) {
    next.done = ev.done
    next.total = ev.total
    next.text = `Checking place ${Math.min((ev.done ?? 0) + 1, ev.total)} of ${ev.total}`
  }
  if (ev.stage === 'write') next.done = next.total = undefined
  return next
}

export const SEARCH_ERROR = 'The connection ended before the answer was complete.'

/** The state a finished stream leaves: the answer, or the reason there is none. */
export function settle(ev: StreamEvent | undefined): Pick<ChatTurn, 'state' | 'response' | 'error'> {
  if (ev?.event === 'answer') return { state: 'done', response: ev.data }
  if (ev?.event === 'error') return { state: 'error', error: errorText(ev.status, ev.detail) }
  if (ev?.event === 'cancelled') return { state: 'error', error: 'Cancelled.' }
  return { state: 'error', error: SEARCH_ERROR }
}

/** Saved between visits: only finished turns (the server needs nothing else), the newest MAX_SAVED_TURNS, and the answer style. */
export interface Saved {
  v: 1
  style: Style
  strict?: boolean
  turns: ChatTurn[]
}

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export function saveChat(store: Store | null, style: Style, turns: ChatTurn[], strict = false): void {
  if (!store) return
  try {
    const done = turns.filter((t) => t.state === 'done' && t.response).slice(-MAX_SAVED_TURNS)
    if (done.length === 0) store.removeItem(STORAGE_KEY)
    else store.setItem(STORAGE_KEY, JSON.stringify({ v: 1, style, strict, turns: done.map(({ progress: _p, ...t }) => t) } satisfies Saved))
  } catch {
    /* storage full or blocked: the chat works without it */
  }
}

const isTurn = (t: unknown): t is ChatTurn => {
  const x = t as ChatTurn
  return !!x && typeof x.id === 'number' && typeof x.message === 'string' && x.state === 'done' && !!x.response && typeof x.response.turn?.question === 'string' && Array.isArray(x.response.places)
}

export function loadChat(store: Store | null): { style: Style; strict: boolean; turns: ChatTurn[] } {
  const empty = { style: 'summary' as Style, strict: false, turns: [] as ChatTurn[] }
  if (!store) return empty
  try {
    const raw = JSON.parse(store.getItem(STORAGE_KEY) ?? 'null') as Partial<Saved> | null
    if (!raw || raw.v !== 1 || !Array.isArray(raw.turns)) return empty
    return { style: raw.style === 'quotes' ? 'quotes' : 'summary', strict: raw.strict === true, turns: raw.turns.filter(isTurn).slice(-MAX_SAVED_TURNS) }
  } catch {
    return empty
  }
}

export function browserStore(): Store | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}
