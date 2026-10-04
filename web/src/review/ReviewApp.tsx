import { useCallback, useEffect, useRef, useState } from 'react'
import { toPath, viewHalf } from './geometry'
import type { GeoJson } from './geometry'

type SetName = 'verify' | 'gate'

interface ClassInfo {
  label: string
  criteria: string
}

interface Item {
  building_id: number
  rank: number
  address: string
  evidence: string
  target: GeoJson
  neighbours: GeoJson[]
  streets: GeoJson[]
  cameras: { x: number; y: number; year: number | null; dist_m: number }[]
  images: { kind: 'photo' | 'crop'; url: string; year: number | null }[]
}

interface Next {
  total: number
  labelled: number
  item: Item | null
}

const SETS: { id: SetName; name: string; blurb: string }[] = [
  { id: 'verify', name: 'Ground-truth check', blurb: 'Random buildings with a street photo. Labels are compared with the parcel data afterwards.' },
  { id: 'gate', name: 'Escalated by the cascade', blurb: 'Buildings the model was least sure about, most uncertain first.' },
]
const CANT_TELL = 'cant_tell'

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(String(r.status))
  return r.json() as Promise<T>
}

function Sketch({ item }: { item: Item }) {
  const half = viewHalf(item.target, item.cameras)
  return (
    <svg className="sketch" viewBox={`${-half} ${-half} ${half * 2} ${half * 2}`} role="img" aria-label="Plan of the building and its surroundings">
      {item.neighbours.map((g, i) => (
        <path key={i} d={toPath(g)} className="sk-neighbour" />
      ))}
      {item.streets.map((g, i) => (
        <path key={i} d={toPath(g)} className="sk-street" />
      ))}
      <path d={toPath(item.target)} className="sk-target" />
      {item.cameras.map((c, i) => (
        <g key={i}>
          <line x1={c.x} y1={-c.y} x2={0} y2={0} className="sk-sight" />
          <circle cx={c.x} cy={-c.y} r={half / 22} className="sk-camera" />
        </g>
      ))}
    </svg>
  )
}

export function ReviewApp() {
  const [classes, setClasses] = useState<ClassInfo[]>([])
  const [setName, setSetName] = useState<SetName>('verify')
  const [next, setNext] = useState<Next | null>(null)
  const [error, setError] = useState('')
  const [showEvidence, setShowEvidence] = useState(false)
  const [busy, setBusy] = useState(false)
  const shownAt = useRef(performance.now())
  const evidenceUsed = useRef(false)

  const load = useCallback(async (name: SetName) => {
    try {
      const n = await api<Next>(`/api/review/next?set_name=${name}`)
      setNext(n)
      setShowEvidence(false)
      evidenceUsed.current = false
      shownAt.current = performance.now()
      setError('')
    } catch (e) {
      setError(
        e instanceof Error && e.message === '404'
          ? 'The review endpoints are off. Restart the API with: STREETWALKER_REVIEW=1 .venv/bin/uvicorn streetwalker.api:app --port 8000'
          : 'Cannot reach the API.',
      )
    }
  }, [])

  useEffect(() => {
    api<ClassInfo[]>('/api/review/classes').then(setClasses).catch(() => undefined)
  }, [])
  useEffect(() => {
    load(setName)
  }, [setName, load])

  const answer = useCallback(
    async (label: string) => {
      if (!next?.item || busy) return
      setBusy(true)
      try {
        await api('/api/review/label', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            building_id: next.item.building_id,
            set_name: setName,
            label,
            seconds: Math.round(((performance.now() - shownAt.current) / 1000) * 10) / 10,
            evidence_shown: evidenceUsed.current,
          }),
        })
        await load(setName)
      } catch {
        setError('Could not save that label. It was not recorded.')
      } finally {
        setBusy(false)
      }
    },
    [next, busy, setName, load],
  )

  const undo = useCallback(async () => {
    if (busy) return
    setBusy(true)
    try {
      await api(`/api/review/undo?set_name=${setName}`, { method: 'POST' })
      await load(setName)
    } catch {
      setError('Could not undo.')
    } finally {
      setBusy(false)
    }
  }, [busy, setName, load])

  const toggleEvidence = useCallback(() => {
    setShowEvidence((s) => !s)
    evidenceUsed.current = true
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= 7 && classes[n - 1]) answer(classes[n - 1].label)
      else if (e.key === '0' || e.key === 'c') answer(CANT_TELL)
      else if (e.key === 'Backspace' || e.key === 'u') undo()
      else if (e.key === 'e') toggleEvidence()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [classes, answer, undo, toggleEvidence])

  const item = next?.item ?? null
  const pct = next && next.total ? Math.round((next.labelled / next.total) * 100) : 0

  return (
    <div className="app review">
      <div className="map review-main">
        {error && <div className="banner error">{error}</div>}
        {!item && next && <div className="loading">All {next.total} buildings in this set are labelled. Compare with the parcel data: .venv/bin/python -m streetwalker.review report</div>}
        {!next && !error && <div className="loading">Loading…</div>}
        {item && (
          <div className="review-body">
            <h2 className="review-title">{item.address}</h2>
            <div className="review-grid">
              <figure>
                <Sketch item={item} />
                <figcaption>
                  Plan, north up. The highlighted outline is the building to label; the dot is where the photo was taken.
                </figcaption>
              </figure>
              {item.images.length === 0 && <p className="muted">No street image exists for this building. Use the plan{showEvidence ? '' : ' and, if you need it, the evidence'}.</p>}
              {item.images.map((im) => (
                <figure key={im.kind}>
                  <img src={im.url} alt={im.kind === 'crop' ? 'Close view aimed at the building' : 'Street photo near the building'} />
                  <figcaption>
                    {im.kind === 'crop' ? 'Close view cut from a panorama, aimed at the building.' : `Street photo${im.year ? ` from ${im.year}` : ''}; it may show a neighbour or be out of date.`}{' '}
                    © Mapillary contributors, CC BY-SA 4.0
                  </figcaption>
                </figure>
              ))}
            </div>
            <button className="linklike" onClick={toggleEvidence}>
              {showEvidence ? 'Hide' : 'Show'} OSM evidence <kbd>E</kbd>
            </button>
            {showEvidence && <pre className="evidence">{item.evidence}</pre>}
          </div>
        )}
      </div>

      <aside className="panel" style={{ width: 400 }}>
        <header>
          <h1>Review</h1>
          <p className="sub">What is this building used for? You are not shown any model answer or the parcel data.</p>
        </header>
        <div className="tabs" role="tablist" aria-label="Queue">
          {SETS.map((s) => (
            <button key={s.id} role="tab" aria-selected={setName === s.id} className={setName === s.id ? 'tab active' : 'tab'} onClick={() => setSetName(s.id)}>
              {s.name}
            </button>
          ))}
        </div>
        <p className="muted">{SETS.find((s) => s.id === setName)?.blurb}</p>
        <div className="progress" aria-label="Progress">
          <div style={{ width: `${pct}%` }} />
        </div>
        <p className="muted">
          {next ? `${next.labelled} of ${next.total} labelled` : ''}
          {item ? ` · now: #${item.rank}` : ''}
        </p>

        <section>
          <h2>Use</h2>
          <div className="choices">
            {classes.map((c, i) => (
              <button key={c.label} className={c.label === CANT_TELL ? 'choice cant' : 'choice'} disabled={!item || busy} onClick={() => answer(c.label)} title={c.criteria}>
                <kbd>{c.label === CANT_TELL ? '0' : i + 1}</kbd>
                <span>
                  <b>{c.label === CANT_TELL ? "Can't tell" : c.label}</b>
                  <small>{c.criteria}</small>
                </span>
              </button>
            ))}
          </div>
        </section>
        <div className="row">
          <button onClick={undo} disabled={busy || !next || next.labelled === 0}>
            Undo last <kbd>⌫</kbd>
          </button>
        </div>
        <footer>Keys: 1 to 7 choose, 0 can't tell, Backspace undoes, E shows the evidence. Time per label is recorded.</footer>
      </aside>
    </div>
  )
}
