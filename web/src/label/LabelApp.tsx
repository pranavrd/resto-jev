import { useCallback, useEffect, useRef, useState } from 'react'
import { ASPECTS, activate, applyKey, choose, complete, emptyDraft } from './keys'
import type { Answers, Aspect, Draft } from './keys'

interface Schema {
  aspects: { aspect: Aspect; definition: string; levels: string[] }[]
}
interface Item {
  item_id: number
  rank: number
  text: string
}
interface Next {
  total: number
  labelled: number
  item: Item | null
}

const BATCH = 1
const LEVEL_NAMES = ['Very negative', 'Negative', 'Mixed or flat', 'Positive', 'Very positive']

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(String(r.status))
  return r.json() as Promise<T>
}

const summary = (a: Answers) => ASPECTS.map((k) => `${k}: ${a[k] === undefined ? '…' : a[k] === null ? 'not mentioned' : LEVEL_NAMES[a[k] as number]}`).join(' · ')

export function LabelApp() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [next, setNext] = useState<Next | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft())
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const shownAt = useRef(performance.now())

  const load = useCallback(async () => {
    try {
      setNext(await api<Next>(`/api/label/next?batch=${BATCH}`))
      setDraft(emptyDraft())
      shownAt.current = performance.now()
      setError('')
    } catch (e) {
      setError(e instanceof Error && e.message === '404' ? 'The labelling endpoints are off. Restart the API with: STREETWALKER_REVIEW=1 .venv/bin/uvicorn streetwalker.api:app --port 8000' : 'Cannot reach the API.')
    }
  }, [])

  useEffect(() => {
    api<Schema>('/api/label/schema').then(setSchema).catch(() => undefined)
    load()
  }, [load])

  const submit = useCallback(
    async (d: Draft) => {
      if (!next?.item || !complete(d.answers) || busy) return
      setBusy(true)
      try {
        await api('/api/label/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_id: next.item.item_id, labels: d.answers, seconds: Math.round(((performance.now() - shownAt.current) / 1000) * 10) / 10 }),
        })
        await load()
      } catch {
        setError('Could not save that label. It was not recorded.')
      } finally {
        setBusy(false)
      }
    },
    [next, busy, load],
  )

  const undo = useCallback(async () => {
    if (busy) return
    setBusy(true)
    try {
      await api(`/api/label/undo?batch=${BATCH}`, { method: 'POST' })
      await load()
    } catch {
      setError('Could not undo.')
    } finally {
      setBusy(false)
    }
  }, [busy, load])

  const press = useCallback(
    (key: string) => {
      const out = applyKey(draft, key)
      setDraft(out.draft)
      if (out.action === 'submit') submit(out.draft)
      if (out.action === 'undo') undo()
    },
    [draft, submit, undo],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (['1', '2', '3', '4', '5', 'n', 'u', 'Enter', 'Backspace', 'ArrowUp', 'ArrowDown', 'Tab'].includes(e.key)) {
        e.preventDefault()
        press(e.key)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [press])

  const item = next?.item ?? null
  const pct = next && next.total ? Math.round((next.labelled / next.total) * 100) : 0
  const ready = complete(draft.answers)

  return (
    <div className="app review">
      <div className="map review-main">
        {error && <div className="banner error">{error}</div>}
        {!item && next && <div className="loading">All items in this batch are labelled. Run: .venv/bin/python -m streetwalker.aspect_labels status</div>}
        {!next && !error && <div className="loading">Loading…</div>}
        {item && (
          <div className="review-body">
            <p className="muted">Item {item.rank} of {next?.total}. Judge only what this text says about each aspect.</p>
            <blockquote className="reviewtext">{item.text}</blockquote>
          </div>
        )}
      </div>

      <aside className="panel" style={{ width: 430 }}>
        <header>
          <h1>Label</h1>
          <p className="sub">How does the reviewer feel about each aspect? You are not shown the stars, the place or any model answer.</p>
        </header>
        <div className="progress" aria-label="Progress">
          <div style={{ width: `${pct}%` }} />
        </div>
        <p className="muted">{next ? `${next.labelled} of ${next.total} labelled` : ''}</p>

        {schema?.aspects.map((s, row) => {
          const value = draft.answers[s.aspect]
          return (
            <section key={s.aspect} className={row === draft.active ? 'aspectrow active' : 'aspectrow'} onClick={() => setDraft((d) => activate(d, row))}>
              <h2>
                {s.aspect} <span className="muted">· {s.definition}</span>
              </h2>
              <div className="levels">
                <button className={value === null ? 'lv on none' : 'lv none'} disabled={!item || busy} onClick={(e) => {
                    e.stopPropagation() // the row's own click handler must not run after this one
                    setDraft((d) => choose(d, row, 'n'))
                  }} title="The review says nothing about this">
                  <kbd>n</kbd> Not mentioned
                </button>
                {LEVEL_NAMES.map((name, level) => (
                  <button
                    key={name}
                    className={value === level ? 'lv on' : 'lv'}
                    disabled={!item || busy}
                    title={s.levels[level]}
                    onClick={(e) => {
                      e.stopPropagation()
                      setDraft((d) => choose(d, row, String(level + 1)))
                    }}
                  >
                    <kbd>{level + 1}</kbd> {name}
                  </button>
                ))}
              </div>
            </section>
          )
        })}

        <p className="muted small">{summary(draft.answers)}</p>
        <div className="row">
          <button className="primary" disabled={!ready || busy || !item} onClick={() => submit(draft)}>
            Save and next <kbd>Enter</kbd>
          </button>
          <button onClick={undo} disabled={busy || !next || next.labelled === 0}>
            Undo last <kbd>u</kbd>
          </button>
        </div>
        <footer>
          Keys: 1 to 5 choose (1 clearly negative, 5 clearly positive), n not mentioned, Backspace steps back, arrows or Tab move between rows, Enter saves, u undoes the last saved item.
          Hover a level for the description. Time per item is recorded.
        </footer>
      </aside>
    </div>
  )
}
