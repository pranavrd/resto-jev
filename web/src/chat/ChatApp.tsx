import { useCallback, useEffect, useRef, useState } from 'react'
import { ENDPOINT, SUGGESTIONS, applyStage, areaLabel, browserStore, buildRequest, canSend, elapsed, errorText, loadChat, monthOf, parseStream, saveChat, settle, splitPlaces } from './chat'
import type { ChatResponse, ChatTurn, Place, Progress, StreamEvent, Style } from './chat'

const ASPECT_ORDER = ['food', 'service', 'atmosphere', 'value']

/** One place the check accepted. Everything from the server is rendered as text, never as markup: reviews are untrusted. */
export function PlaceCard({ place }: { place: Place }) {
  return (
    <article className="chat-place">
      <h3>
        {place.name || 'Unnamed place'} <span className="chat-meta">{place.kind} · {areaLabel(place.area)}</span>
      </h3>
      {place.summary ? (
        <p className="chat-summary">
          <span className="chat-tag">Model-written, not checked</span> {place.summary}
        </p>
      ) : null}
      {place.quotes.map((q) => (
        <blockquote key={q.review_id} className="chat-quote">
          “{q.quote}” <cite>{monthOf(q.date)}, verbatim</cite>
        </blockquote>
      ))}
      {Object.keys(place.standing).length ? (
        <ul className="chat-standing" aria-label="Provisional ratings">
          {ASPECT_ORDER.filter((a) => place.standing[a]).map((a) => (
            <li key={a}>
              <b>{a}</b> {place.standing[a].words}
            </li>
          ))}
        </ul>
      ) : (
        <p className="chat-muted">No ratings.</p>
      )}
    </article>
  )
}

/** What the server has said so far about the answer being worked on. */
export function PendingView({ progress, seconds, onCancel }: { progress?: Progress; seconds: string; onCancel: () => void }) {
  return (
    <div className="chat-pending" role="status">
      {progress?.followup && progress.question ? (
        <p className="chat-understood">
          Understood as: <q>{progress.question}</q>
        </p>
      ) : null}
      {progress?.searched_for ? <p className="chat-searched">Searching for: {progress.searched_for}.</p> : null}
      {progress?.places?.length ? <p className="chat-muted">Found: {progress.places.join(', ')}.</p> : null}
      <p>
        {progress?.text || 'Starting'}… {seconds} <button onClick={onCancel}>Cancel</button>
      </p>
    </div>
  )
}

/** The assistant's whole answer to one message. */
export function AnswerView({ r }: { r: ChatResponse }) {
  const { shown, other } = splitPlaces(r.places)
  return (
    <div className="chat-answer">
      {r.followup ? (
        <p className="chat-understood">
          Understood as: <q>{r.question}</q>
        </p>
      ) : null}
      {r.searched_for ? <p className="chat-searched">Searched for: {r.searched_for}.</p> : null}
      {r.alphabetical && shown.length ? <p className="chat-note">Listed alphabetically: not a ranking, and not a recommendation.</p> : null}
      {r.models?.check === 'k2' ? <p className="chat-muted">Strict matching was on: fewer wrong places, and some right ones may be missing.</p> : null}
      {r.lowest_first && shown.length ? (
        <p className="chat-note">Lowest scores first, among places with at least 10 reviews. An AI scorer's reading of what reviewers wrote, provisional: a low score is not a verdict on the place.</p>
      ) : null}
      {shown.map((p) => (
        <PlaceCard key={p.id} place={p} />
      ))}
      {r.notice ? <p className="chat-notice">{r.notice}</p> : null}
      {other.length ? <p className="chat-other">Returned by the search but not judged to answer: {other.map((p) => p.name || 'unnamed').join(', ')}.</p> : null}
      {r.dropped.quotes > 0 ? (
        <p className="chat-muted">
          {r.dropped.quotes} quote{r.dropped.quotes === 1 ? '' : 's'} the model offered {r.dropped.quotes === 1 ? 'was' : 'were'} left out because they were not word for word from the reviews.
        </p>
      ) : null}
      <p className="chat-caveat">{r.caveat}</p>
    </div>
  )
}

export function ChatApp() {
  const saved = useRef(loadChat(browserStore()))
  const [turns, setTurns] = useState<ChatTurn[]>(saved.current.turns)
  const [draft, setDraft] = useState('')
  const [style, setStyle] = useState<Style>(saved.current.style)
  const [strict, setStrict] = useState<boolean>(saved.current.strict)
  const [now, setNow] = useState(Date.now())
  const nextId = useRef(Math.max(0, ...saved.current.turns.map((t) => t.id)) + 1)
  const ctl = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const busy = turns.some((t) => t.state === 'pending')

  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [busy])

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns])

  // The conversation is kept in this browser only (finished turns and the style); New chat clears it.
  useEffect(() => saveChat(browserStore(), style, turns, strict), [style, turns, strict])

  const update = useCallback((id: number, patch: Partial<ChatTurn>) => setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t))), [])

  const send = useCallback(
    async (text: string) => {
      if (!canSend(text) || busy) return
      const body = buildRequest(text, style, turns, strict)
      const id = nextId.current++
      const controller = new AbortController()
      ctl.current = controller
      setTurns((ts) => [...ts, { id, message: body.question, style, state: 'pending', startedAt: Date.now() }])
      setNow(Date.now())
      setDraft('')
      try {
        const r = await fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: controller.signal })
        if (!r.ok || !r.body) {
          let detail: unknown
          try {
            detail = ((await r.json()) as { detail?: unknown }).detail
          } catch {
            detail = undefined
          }
          update(id, { state: 'error', error: errorText(r.status, typeof detail === 'string' ? detail : undefined) })
          return
        }
        const reader = r.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let last: StreamEvent | undefined
        const take = (events: StreamEvent[]) => {
          for (const ev of events) {
            if (ev.event === 'stage') setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, progress: applyStage(t.progress, ev) } : t)))
            else last = ev
          }
        }
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const parsed = parseStream(buffer)
          buffer = parsed.rest
          take(parsed.events)
        }
        take(parseStream(buffer + decoder.decode() + '\n').events)
        update(id, { ...settle(last), progress: undefined })
      } catch {
        update(id, { state: 'error', error: controller.signal.aborted ? 'Cancelled.' : errorText(null), progress: undefined })
      }
    },
    [busy, style, strict, turns, update],
  )

  const cancel = () => ctl.current?.abort()
  const reset = () => {
    ctl.current?.abort()
    setTurns([])
    setDraft('')
  }

  return (
    <main className="chat">
      <p className="chat-banner" role="note">
        <b>Provisional.</b> Ratings come from an AI scorer and are not validated against people. Reviews end in January 2022. Private, local use.
      </p>
      <div className="chat-scroll">
        <div className="chat-thread" aria-live="polite">
          {turns.length === 0 ? (
            <section className="chat-empty">
              <h1>Ask about places</h1>
              <p className="muted">Restaurants, bars and cafes in Rittenhouse, East Passyunk and Roxborough, and what reviewers said. You can follow up: “what about in Roxborough?”, “only the cheap ones”.</p>
              <div className="chat-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} disabled={busy}>
                    {s}
                  </button>
                ))}
              </div>
            </section>
          ) : null}
          {turns.map((t) => (
            <div key={t.id} className="chat-turn">
              <p className="chat-user">{t.message}</p>
              {t.state === 'pending' ? <PendingView progress={t.progress} seconds={elapsed(now - t.startedAt)} onCancel={cancel} /> : null}
              {t.state === 'error' ? (
                <p className="chat-error" role="alert">
                  {t.error} {t.error !== 'Cancelled.' ? <button onClick={() => send(t.message)} disabled={busy}>Try again</button> : null}
                </p>
              ) : null}
              {t.state === 'done' && t.response ? <AnswerView r={t.response} /> : null}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>
      <form
        className="chat-compose"
        onSubmit={(e) => {
          e.preventDefault()
          send(draft)
        }}
      >
        <div className="chat-options">
          <div className="seg" role="group" aria-label="Answer style">
            <button type="button" className={style === 'summary' ? 'on' : ''} aria-pressed={style === 'summary'} onClick={() => setStyle('summary')}>
              Summaries
            </button>
            <button type="button" className={style === 'quotes' ? 'on' : ''} aria-pressed={style === 'quotes'} onClick={() => setStyle('quotes')} title="Verbatim quotes only, no model-written text, faster">
              Quotes only
            </button>
          </div>
          <button
            type="button"
            className={strict ? 'on' : ''}
            aria-pressed={strict}
            onClick={() => setStrict(!strict)}
            title="Ask a second question of every place the check accepts: fewer wrong places, but it also misses more right ones (decision 0032)"
          >
            Strict matching
          </button>
          <button type="button" onClick={reset} disabled={turns.length === 0 && !draft}>
            New chat
          </button>
        </div>
        <div className="chat-row">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send(draft)
              }
            }}
            placeholder="Ask about places, or follow up on the last answer"
            aria-label="Your question"
            rows={2}
          />
          <button type="submit" className="primary" disabled={busy || !canSend(draft)}>
            Send
          </button>
        </div>
        {draft.trim().length > 500 ? <p className="chat-error">Too long: questions are limited to 500 characters.</p> : null}
      </form>
    </main>
  )
}
