import type { MapViewState } from 'deck.gl'
import { DeckGL, MapView, PathLayer, PolygonLayer, ScatterplotLayer, TripsLayer, WebMercatorViewport } from 'deck.gl'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { countThrough, formatClock, positionAt } from './replay'
import type { AreaData, IndexEntry, LngLat, Poly, Step } from './types'

type Mode = 'signal' | 'landuse'
type Color = [number, number, number] | [number, number, number, number]

const UNSEEN: Color = [36, 43, 56]
const SIGNAL_COLORS: Record<number, Color> = { 2: [255, 176, 32], 1: [96, 165, 250], 0: [148, 163, 184] }
const SIGNAL_LABELS: Record<number, string> = {
  2: 'Business POI linked',
  1: 'OSM use tag or name',
  0: 'No OSM use signal',
}
const LU_COLORS: Record<string, Color> = {
  residential: [148, 163, 184],
  mixed: [192, 132, 252],
  commercial: [251, 146, 60],
  civic: [74, 222, 128],
  industrial: [180, 110, 20],
  vacant: [90, 104, 125],
  other: [226, 232, 240],
}
const SPEEDS = [30, 60, 120, 300, 600, 1200]
const PANEL_WIDTH = 380

const css = (c: Color) => `rgb(${c[0]} ${c[1]} ${c[2]})`

function centroid(rings: number[][][]): LngLat {
  const ring = rings[0]
  let x = 0
  let y = 0
  for (const [lng, lat] of ring) {
    x += lng
    y += lat
  }
  return [x / ring.length, y / ring.length]
}

function fitView(bounds: AreaData['bounds'], width: number, height: number) {
  const [xmin, ymin, xmax, ymax] = bounds
  const vp = new WebMercatorViewport({ width, height })
  const { longitude, latitude, zoom } = vp.fitBounds(
    [
      [xmin, ymin],
      [xmax, ymax],
    ],
    { padding: 36 },
  )
  return { longitude, latitude, zoom, pitch: 0, bearing: 0 }
}

export function App() {
  const [index, setIndex] = useState<IndexEntry[]>([])
  const [slug, setSlug] = useState<string>('')
  const [data, setData] = useState<AreaData | null>(null)
  const [error, setError] = useState<string>('')
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(120)
  const [mode, setMode] = useState<Mode>('signal')
  const [selected, setSelected] = useState<number | null>(null)
  const [viewState, setViewState] = useState<MapViewState>({ longitude: -75.17, latitude: 39.95, zoom: 15 })
  const timeRef = useRef(0)

  useEffect(() => {
    fetch('/data/index.json')
      .then((r) => r.json())
      .then((idx: IndexEntry[]) => {
        setIndex(idx)
        setSlug(idx[0]?.slug ?? '')
      })
      .catch(() => setError('No replay data found. Run: python -m streetwalker.export_replay'))
  }, [])

  useEffect(() => {
    if (!slug) return
    setData(null)
    setPlaying(false)
    setSelected(null)
    timeRef.current = 0
    setTime(0)
    fetch(`/data/${slug}.json`)
      .then((r) => r.json())
      .then((d: AreaData) => {
        setData(d)
        setViewState(fitView(d.bounds, window.innerWidth - PANEL_WIDTH, window.innerHeight))
      })
      .catch(() => setError(`Could not load ${slug}.json`))
  }, [slug])

  // Animation clock: advances simulated time by speed x real elapsed time.
  useEffect(() => {
    if (!playing || !data) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      const next = Math.min(data.duration_s, timeRef.current + dt * speed)
      timeRef.current = next
      setTime(next)
      if (next >= data.duration_s) setPlaying(false)
      else raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, data])

  const seek = useCallback((t: number) => {
    timeRef.current = t
    setTime(t)
  }, [])

  const togglePlay = useCallback(() => {
    if (!data) return
    if (timeRef.current >= data.duration_s) seek(0)
    setPlaying((p) => !p)
  }, [data, seek])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (e.code === 'Space' && tag !== 'INPUT' && tag !== 'SELECT' && tag !== 'BUTTON') {
        e.preventDefault()
        togglePlay()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [togglePlay])

  const derived = useMemo(() => {
    if (!data) return null
    return {
      buildingTimes: data.buildings.map((b) => b.t),
      stepEnds: data.steps.map((s) => s.t1),
      centroids: data.buildings.map((_, i) => centroid(data.polys.find((p) => p.b === i)!.g)),
    }
  }, [data])

  const encountered = derived ? countThrough(derived.buildingTimes, time) : 0
  const stepsDone = derived ? countThrough(derived.stepEnds, time) : 0
  const walker = data ? positionAt(data.steps, time) : null
  const recent = data ? data.buildings.slice(Math.max(0, encountered - 8), encountered).reverse() : []

  const layers = useMemo(() => {
    if (!data || !derived) return []
    const fill = (d: Poly): Color => {
      const b = data.buildings[d.b]
      if (b.t > time) return UNSEEN
      return mode === 'signal' ? SIGNAL_COLORS[b.sig] : (LU_COLORS[b.lu] ?? LU_COLORS.other)
    }
    return [
      new PathLayer<LngLat[]>({
        id: 'streets',
        data: data.streets,
        getPath: (d) => d,
        getColor: [70, 80, 98],
        getWidth: 1.5,
        widthUnits: 'pixels',
      }),
      new PathLayer<Step>({
        id: 'walked',
        data: data.steps,
        getPath: (d) => d.p,
        getColor: (d): Color => (d.t1 > time ? [0, 0, 0, 0] : d.r ? [250, 190, 80, 90] : [45, 212, 191, 200]),
        getWidth: 3,
        widthUnits: 'pixels',
        updateTriggers: { getColor: [stepsDone] },
      }),
      new PolygonLayer<Poly>({
        id: 'buildings',
        data: data.polys,
        getPolygon: (d) => d.g,
        getFillColor: fill,
        getLineColor: [12, 16, 24, 220],
        lineWidthMinPixels: 0.6,
        stroked: true,
        pickable: true,
        onClick: (info) => setSelected(info.object ? (info.object as Poly).b : null),
        updateTriggers: { getFillColor: [encountered, mode] },
      }),
      new PolygonLayer<Poly>({
        id: 'selected',
        data: selected === null ? [] : data.polys.filter((p) => p.b === selected),
        getPolygon: (d) => d.g,
        filled: false,
        stroked: true,
        getLineColor: [255, 255, 255],
        lineWidthMinPixels: 2.5,
      }),
      new TripsLayer<Step>({
        id: 'trail',
        data: data.steps,
        getPath: (d) => d.p,
        getTimestamps: (d) => d.t,
        getColor: [255, 255, 255],
        widthMinPixels: 4,
        capRounded: true,
        jointRounded: true,
        fadeTrail: true,
        trailLength: 150,
        currentTime: time,
      }),
      new ScatterplotLayer<{ i: number; age: number }>({
        id: 'pulses',
        data: data.buildings
          .map((b, i) => ({ i, age: time - b.t }))
          .slice(Math.max(0, encountered - 10), encountered),
        getPosition: (d) => derived.centroids[d.i],
        getRadius: (d) => 6 + Math.min(d.age, 120) / 4,
        radiusUnits: 'pixels',
        getFillColor: [0, 0, 0, 0],
        stroked: true,
        getLineColor: (d): Color => [255, 255, 255, Math.max(0, 200 - d.age * 1.6)],
        getLineWidth: 1.5,
        lineWidthUnits: 'pixels',
      }),
      new ScatterplotLayer<LngLat>({
        id: 'walker',
        data: walker ? [walker] : [],
        getPosition: (d) => d,
        getRadius: 7,
        radiusUnits: 'pixels',
        getFillColor: [255, 255, 255],
        stroked: true,
        getLineColor: [45, 212, 191],
        getLineWidth: 3,
        lineWidthUnits: 'pixels',
      }),
    ]
  }, [data, derived, time, mode, selected, encountered, stepsDone, walker])

  const selectedBuilding = data && selected !== null ? data.buildings[selected] : null
  const legend =
    mode === 'signal'
      ? ([2, 1, 0] as const).map((k) => ({ label: SIGNAL_LABELS[k], color: SIGNAL_COLORS[k] }))
      : Object.entries(LU_COLORS).map(([label, color]) => ({ label, color }))

  return (
    <div className="app">
      <div className="map">
        {data && (
          <DeckGL
            views={new MapView({ repeat: false })}
            viewState={viewState}
            onViewStateChange={({ viewState: vs }) => setViewState(vs as MapViewState)}
            controller
            layers={layers}
            getTooltip={({ object }) => {
              const poly = object as Poly | undefined
              if (!poly) return null
              const b = data.buildings[poly.b]
              return b.t > time ? 'Not yet surveyed' : `${b.addr}${b.kinds ? ` · ${b.kinds}` : ''}`
            }}
          />
        )}
        {!data && !error && <div className="loading">Loading…</div>}
        {error && <div className="loading error">{error}</div>}
      </div>

      <aside className="panel" style={{ width: PANEL_WIDTH }}>
        <header>
          <h1>StreetWalker</h1>
          <p className="sub">Replay of the survey walk</p>
        </header>

        <div className="tabs" role="tablist" aria-label="Survey area">
          {index.map((a) => (
            <button
              key={a.slug}
              role="tab"
              aria-selected={a.slug === slug}
              className={a.slug === slug ? 'tab active' : 'tab'}
              onClick={() => setSlug(a.slug)}
            >
              {a.name}
            </button>
          ))}
        </div>
        {data && <p className="muted">{data.profile}</p>}

        <section className="controls">
          <div className="row">
            <button className="primary" onClick={togglePlay} disabled={!data}>
              {playing ? 'Pause' : time > 0 && data && time >= data.duration_s ? 'Replay' : 'Play'}
            </button>
            <button onClick={() => seek(0)} disabled={!data}>
              Restart
            </button>
            <label className="speed">
              Speed
              <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                {SPEEDS.map((s) => (
                  <option key={s} value={s}>
                    {s}x
                  </option>
                ))}
              </select>
            </label>
          </div>
          <input
            type="range"
            aria-label="Simulated time"
            min={0}
            max={data?.duration_s ?? 1}
            step={1}
            value={time}
            onChange={(e) => seek(Number(e.target.value))}
            disabled={!data}
          />
          <div className="clock">
            <span>{formatClock(time)}</span>
            <span className="muted">of {formatClock(data?.duration_s ?? 0)}</span>
          </div>
        </section>

        <section className="stats">
          <div>
            <b>{encountered}</b>
            <span>of {data?.buildings.length ?? 0} buildings surveyed</span>
          </div>
          <div>
            <b>{data ? ((time * data.speed_ms) / 1000).toFixed(1) : '0.0'} km</b>
            <span>walked at 1.4 m/s</span>
          </div>
        </section>

        <section>
          <h2>Colour</h2>
          <div className="seg">
            <button className={mode === 'signal' ? 'on' : ''} onClick={() => setMode('signal')}>
              Evidence signal
            </button>
            <button className={mode === 'landuse' ? 'on' : ''} onClick={() => setMode('landuse')}>
              Land use (ground truth)
            </button>
          </div>
          <ul className="legend">
            {legend.map((l) => (
              <li key={l.label}>
                <i style={{ background: css(l.color) }} />
                {l.label}
              </li>
            ))}
            <li>
              <i style={{ background: css(UNSEEN) }} />
              not yet surveyed
            </li>
          </ul>
          {mode === 'landuse' && <p className="muted">Ground truth is shown for development; the classifier never sees it.</p>}
        </section>

        <section>
          <h2>{selectedBuilding ? 'Selected building' : 'Just surveyed'}</h2>
          {selectedBuilding ? (
            <>
              <p className="addr">{selectedBuilding.addr}</p>
              {selectedBuilding.t > time && <p className="muted">Not yet surveyed.</p>}
              <pre className="evidence">{selectedBuilding.text}</pre>
              <button onClick={() => setSelected(null)}>Clear selection</button>
            </>
          ) : recent.length ? (
            <ol className="recent">
              {recent.map((b) => (
                <li key={b.seq}>
                  <i style={{ background: css(SIGNAL_COLORS[b.sig]) }} />
                  <span>{b.addr}</span>
                  {b.kinds && <em>{b.kinds}</em>}
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">Press Play (or Space). Click a building to read its evidence.</p>
          )}
        </section>

        <footer>{data?.attribution}</footer>
      </aside>
    </div>
  )
}
