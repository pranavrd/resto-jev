import type { MapViewState } from 'deck.gl'
import { DeckGL, MapView, PathLayer, PolygonLayer, ScatterplotLayer, WebMercatorViewport } from 'deck.gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { distanceM, extent } from './geo'
import type { LngLat } from './geo'
import { MODE_COLORS, css, kindColor, topMode } from './kinds'
import type { Rgb } from './kinds'
import { DEFAULT_FILTERS, isFiltered, toParams, toggleKind } from './query'
import type { Filters, Sort } from './query'
import type { Meta, Place, PlaceDetail, PlacesResponse, Stop, StopCollection } from './types'

const PANEL_WIDTH = 400
const WALK_M = 400
const DEBOUNCE_MS = 250
const GHOST: Rgb = [148, 163, 184] // places the filters exclude: hollow, so they do not read as bus stops

interface Backdrop {
  streets: LngLat[][]
  polys: { g: number[][][] }[]
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal })
  if (!r.ok) throw new Error(`${url}: ${r.status}`)
  return r.json() as Promise<T>
}

const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
const title = (p: Place) => p.name ?? p.address ?? 'Unnamed place'
const pos = (p: Place): LngLat => [p.lng, p.lat]
const metres = (m: number | null) => (m === null ? 'none within 2 km' : m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`)

const MIN_FIT_PX = 240 // fitBounds asserts when the padded target is empty, e.g. before the first layout

function fitPoints(points: LngLat[], width: number, height: number): MapViewState | null {
  const box = extent(points)
  if (!box) return null
  const [w, s, e, n] = box
  const viewport = new WebMercatorViewport({ width: Math.max(width, MIN_FIT_PX), height: Math.max(height, MIN_FIT_PX) })
  const { longitude, latitude, zoom } = viewport.fitBounds(
    [
      [w, s],
      [e, n],
    ],
    { padding: 60, maxZoom: 17 },
  )
  return { longitude, latitude, zoom, pitch: 0, bearing: 0 }
}

const RAIL_OPTIONS: [string, number | null][] = [['Any distance', null], ['200 m', 200], ['400 m', 400], ['800 m', 800]]
const TRIPS_OPTIONS: [string, number | null][] = [['Any', null], ['500 or more', 500], ['1,000 or more', 1000], ['2,000 or more', 2000]]
const SOURCE_OPTIONS: [string, Filters['source']][] = [
  ['Any', ''],
  ['Both OSM and licence', 'both'],
  ['OSM only', 'osm'],
  ['Licence only', 'licence'],
]
const CONFIDENCE_OPTIONS: [string, Filters['minConfidence']][] = [['Any', ''], ['Medium or high', 'medium'], ['High only', 'high']]

export function PlacesApp() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [everything, setEverything] = useState<Place[]>([])
  const [stops, setStops] = useState<Stop[]>([])
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [result, setResult] = useState<PlacesResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [backdrop, setBackdrop] = useState<Backdrop | null>(null)
  const [showStops, setShowStops] = useState(true)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<PlaceDetail | null>(null)
  const [hoverId, setHoverId] = useState<number | null>(null)
  const [viewState, setViewState] = useState<MapViewState>({ longitude: -75.17, latitude: 39.95, zoom: 12 })

  const mapRef = useRef<HTMLDivElement>(null)
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))
  const debounced = useDebounced(filters, DEBOUNCE_MS)
  const key = toParams(debounced).toString()

  // One-off loads: metadata, the whole census (the faint "everything" layer and the fit extents) and SEPTA stops.
  useEffect(() => {
    const ctl = new AbortController()
    const down = (e: unknown) => {
      if (!isAbort(e)) setError('Cannot reach the API. Start it with: .venv/bin/uvicorn streetwalker.api:app --port 8000')
    }
    getJson<Meta>('/api/meta', ctl.signal).then(setMeta).catch(down)
    getJson<PlacesResponse>(`/api/places?${toParams(DEFAULT_FILTERS)}`, ctl.signal)
      .then((r) => setEverything(r.items))
      .catch(down)
    getJson<StopCollection>('/api/transit/stops', ctl.signal)
      .then((c) =>
        setStops(
          c.features.map((f) => ({
            id: f.id,
            name: f.properties.name,
            lng: f.geometry.coordinates[0],
            lat: f.geometry.coordinates[1],
            modes: f.properties.modes,
            routes: f.properties.routes,
            trips: f.properties.weekday_trips,
          })),
        ),
      )
      .catch(down)
    return () => ctl.abort()
  }, [])

  // The search itself. A newer query aborts the one in flight, so a slow answer cannot overwrite a fresh one.
  useEffect(() => {
    const ctl = new AbortController()
    setLoading(true)
    getJson<PlacesResponse>(`/api/places?${key}`, ctl.signal)
      .then((r) => {
        setResult(r)
        setError('')
        setLoading(false)
      })
      .catch((e) => {
        if (isAbort(e)) return
        setLoading(false)
        setError(`Search failed: ${e instanceof Error ? e.message : 'unknown error'}`)
      })
    return () => ctl.abort()
  }, [key])

  // Footprints and streets for context, from the replay export (OSM and City data), when one area is chosen.
  useEffect(() => {
    setBackdrop(null)
    if (!filters.area) return
    const ctl = new AbortController()
    getJson<Backdrop>(`/data/${filters.area}.json`, ctl.signal)
      .then((d) => setBackdrop({ streets: d.streets, polys: d.polys }))
      .catch(() => undefined) // optional: without the export the map shows places and stops only
    return () => ctl.abort()
  }, [filters.area])

  // Fit the view to the chosen area (or all three) once the census is loaded.
  const areaKey = filters.area
  useEffect(() => {
    const here = everything.filter((p) => !areaKey || p.area === areaKey)
    const box = mapRef.current
    const next = fitPoints(here.map(pos), box?.clientWidth ?? window.innerWidth - PANEL_WIDTH, box?.clientHeight ?? window.innerHeight)
    if (next) setViewState(next)
  }, [areaKey, everything])

  // A text search zooms to what it found; filter-only changes leave the view where the user put it.
  useEffect(() => {
    if (!result || !debounced.q.trim() || !result.items.length) return
    const box = mapRef.current
    const next = fitPoints(result.items.map(pos), box?.clientWidth ?? window.innerWidth - PANEL_WIDTH, box?.clientHeight ?? window.innerHeight)
    if (next) setViewState({ ...next, transitionDuration: 400 })
  }, [result, debounced.q])

  useEffect(() => {
    setDetail(null)
    if (selectedId === null) return
    const ctl = new AbortController()
    getJson<PlaceDetail>(`/api/places/${selectedId}`, ctl.signal)
      .then(setDetail)
      .catch(() => undefined)
    return () => ctl.abort()
  }, [selectedId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Choosing from the list recentres the map on the place (map clicks leave the view alone).
  const flyTo = (p: Place) => {
    setSelectedId(p.id)
    setViewState((v) => ({ ...v, longitude: p.lng, latitude: p.lat, zoom: Math.max(v.zoom, 16), transitionDuration: 500 }))
  }

  const items = result?.items ?? []
  const matchIds = useMemo(() => new Set(items.map((p) => p.id)), [items])
  const selected = useMemo(() => everything.find((p) => p.id === selectedId) ?? null, [everything, selectedId])
  const inReach = useMemo(
    () => (selected ? stops.filter((s) => distanceM([s.lng, s.lat], pos(selected)) <= WALK_M) : []),
    [stops, selected],
  )
  const reachIds = useMemo(() => new Set(inReach.map((s) => s.id)), [inReach])

  const layers = useMemo(() => {
    const ghost = everything.filter((p) => !matchIds.has(p.id) && (!areaKey || p.area === areaKey))
    return [
      new PathLayer<LngLat[]>({
        id: 'streets',
        data: backdrop?.streets ?? [],
        getPath: (d) => d,
        getColor: [58, 68, 86],
        getWidth: 1.2,
        widthUnits: 'pixels',
      }),
      new PolygonLayer<{ g: number[][][] }>({
        id: 'footprints',
        data: backdrop?.polys ?? [],
        getPolygon: (d) => d.g,
        getFillColor: [30, 38, 50],
        getLineColor: [12, 16, 24, 220],
        lineWidthMinPixels: 0.5,
        stroked: true,
      }),
      new ScatterplotLayer<Stop>({
        id: 'stops',
        data: showStops ? stops : [],
        getPosition: (d) => [d.lng, d.lat],
        getRadius: (d) => Math.min(7, 2.2 + Math.sqrt(d.trips) / 9),
        radiusUnits: 'pixels',
        getFillColor: (d): [number, number, number, number] => [...MODE_COLORS[topMode(d.modes)], selected && !reachIds.has(d.id) ? 70 : 200],
        stroked: true,
        getLineColor: (d): [number, number, number, number] => (reachIds.has(d.id) ? [255, 255, 255, 255] : [0, 0, 0, 0]),
        lineWidthMinPixels: 1.5,
        pickable: true,
        updateTriggers: { getFillColor: [selectedId], getLineColor: [selectedId] },
      }),
      new ScatterplotLayer<Place>({
        id: 'ghost',
        data: ghost,
        getPosition: pos,
        getRadius: 4,
        radiusUnits: 'pixels',
        filled: false,
        stroked: true,
        getLineColor: [...GHOST, 200],
        lineWidthMinPixels: 1.2,
      }),
      new ScatterplotLayer<Place>({
        id: 'reach',
        data: selected ? [selected] : [],
        getPosition: pos,
        getRadius: WALK_M,
        radiusUnits: 'meters',
        filled: true,
        getFillColor: [255, 255, 255, 14],
        stroked: true,
        getLineColor: [255, 255, 255, 140],
        lineWidthMinPixels: 1.5,
      }),
      new ScatterplotLayer<Place>({
        id: 'places',
        data: items,
        getPosition: pos,
        getRadius: (d) => (d.id === selectedId || d.id === hoverId ? 9 : 6),
        radiusUnits: 'pixels',
        getFillColor: (d): [number, number, number, number] => [...kindColor(d.kind), 245],
        stroked: true,
        getLineColor: (d): [number, number, number, number] => (d.id === selectedId ? [255, 255, 255, 255] : [8, 11, 16, 230]),
        getLineWidth: (d) => (d.id === selectedId ? 3 : 1),
        lineWidthUnits: 'pixels',
        pickable: true,
        onClick: (info) => setSelectedId(info.object ? (info.object as Place).id : null),
        onHover: (info) => setHoverId(info.object ? (info.object as Place).id : null),
        updateTriggers: { getRadius: [selectedId, hoverId], getLineColor: [selectedId], getLineWidth: [selectedId] },
      }),
    ]
  }, [everything, items, matchIds, areaKey, backdrop, stops, showStops, selected, selectedId, hoverId, reachIds])

  const areaCounts = new Map(meta?.areas.map((a) => [a.slug, a]))
  const kindList = meta?.kinds ?? []
  const attribution = result?.attribution ?? meta?.attribution ?? []
  const sorts: [string, Sort][] = [
    ['Name', ''],
    ['Most transit service', 'transit'],
    ...(filters.q.trim() ? ([['Best match', 'relevance']] as [string, Sort][]) : []),
  ]
  const sortValue = filters.sort === 'relevance' && !filters.q.trim() ? '' : filters.sort

  return (
    <div className="app">
      <div className="map" ref={mapRef}>
        <DeckGL
          views={new MapView({ repeat: false })}
          viewState={viewState}
          onViewStateChange={({ viewState: vs }) => setViewState(vs as MapViewState)}
          controller
          layers={layers}
          getTooltip={({ object, layer }) => {
            if (!object) return null
            if (layer?.id === 'stops') {
              const s = object as Stop
              return `${s.name}\n${s.routes.join(', ')} · ${s.trips} weekday departures`
            }
            if (layer?.id === 'places') {
              const p = object as Place
              return `${title(p)}\n${p.kind}${p.neighborhood ? ` · ${p.neighborhood}` : ''}`
            }
            return null
          }}
        />
        {error && <div className="banner error">{error}</div>}

        {selected && (
          <aside className="card" aria-label="Selected place">
            <button className="close" onClick={() => setSelectedId(null)} aria-label="Close">
              ×
            </button>
            <h2 className="card-title">
              <i style={{ background: css(kindColor(selected.kind)) }} />
              {title(selected)}
            </h2>
            <p className="muted">
              {selected.kind}
              {selected.kind_source === 'jev' ? ' (inferred by Jev from the licence)' : ''}
              {selected.neighborhood ? ` · ${selected.neighborhood}` : ''}
            </p>
            {selected.address && <p>{selected.address}</p>}
            <dl className="facts">
              <dt>Listed by</dt>
              <dd>{selected.sources.map((s) => (s === 'osm' ? 'OpenStreetMap' : 'City licence')).join(' and ')}</dd>
              <dt>Confidence</dt>
              <dd>
                {selected.confidence}
                {detail?.match_basis ? ` (matched on ${detail.match_basis})` : ''}
              </dd>
              {detail?.licence_name && detail.licence_name !== selected.name && (
                <>
                  <dt>Licensed as</dt>
                  <dd>{detail.licence_name}</dd>
                </>
              )}
            </dl>
            <h3>Transit</h3>
            <dl className="facts">
              <dt>Nearest stop</dt>
              <dd>
                {selected.transit.nearest_stop_name} · {metres(selected.transit.nearest_stop_m)}
              </dd>
              <dt>Nearest rail</dt>
              <dd>
                {selected.transit.nearest_rail_name ? `${selected.transit.nearest_rail_name} · ` : ''}
                {metres(selected.transit.nearest_rail_m)}
              </dd>
              <dt>Within 400 m</dt>
              <dd>
                {selected.transit.stops_400m} stops, {selected.transit.weekday_trips_400m.toLocaleString()} weekday departures
              </dd>
            </dl>
            <div className="chips">
              {selected.transit.routes_400m.map((r) => (
                <span key={r} className="chip">
                  {r}
                </span>
              ))}
            </div>
            <p className="muted small">Straight-line distances, one weekday (Wednesday 2026-10-07). Ring = 400 m.</p>
          </aside>
        )}
      </div>

      <aside className="panel" style={{ width: PANEL_WIDTH }}>
        <header>
          <h1>Places</h1>
          <p className="sub">Restaurant census of three Philadelphia areas, with SEPTA access</p>
        </header>

        <input
          type="search"
          className="search"
          placeholder="Search name or address"
          aria-label="Search places"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />

        <div className="tabs" role="tablist" aria-label="Area">
          <button role="tab" aria-selected={!filters.area} className={!filters.area ? 'tab active' : 'tab'} onClick={() => set({ area: '' })}>
            All areas
          </button>
          {meta?.areas.map((a) => (
            <button
              key={a.slug}
              role="tab"
              aria-selected={filters.area === a.slug}
              className={filters.area === a.slug ? 'tab active' : 'tab'}
              onClick={() => set({ area: a.slug })}
            >
              {a.name} <span className="count">{a.places}</span>
            </button>
          ))}
        </div>
        {filters.area && <p className="muted">{areaCounts.get(filters.area)?.profile}</p>}

        <section>
          <h2>Kind</h2>
          <div className="chips">
            {kindList.map((k) => (
              <button
                key={k.kind}
                className={filters.kinds.includes(k.kind) ? 'chip kind on' : 'chip kind'}
                aria-pressed={filters.kinds.includes(k.kind)}
                onClick={() => set({ kinds: toggleKind(filters.kinds, k.kind) })}
              >
                <i style={{ background: css(kindColor(k.kind)) }} />
                {k.kind} <span className="count">{k.places}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="grid2">
          <label>
            Rail stop within
            <select value={String(filters.maxRailM)} onChange={(e) => set({ maxRailM: e.target.value === 'null' ? null : Number(e.target.value) })}>
              {RAIL_OPTIONS.map(([label, v]) => (
                <option key={label} value={String(v)}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Weekday departures, 400 m
            <select value={String(filters.minTrips)} onChange={(e) => set({ minTrips: e.target.value === 'null' ? null : Number(e.target.value) })}>
              {TRIPS_OPTIONS.map(([label, v]) => (
                <option key={label} value={String(v)}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Listed by
            <select value={filters.source} onChange={(e) => set({ source: e.target.value as Filters['source'] })}>
              {SOURCE_OPTIONS.map(([label, v]) => (
                <option key={label} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Confidence
            <select value={filters.minConfidence} onChange={(e) => set({ minConfidence: e.target.value as Filters['minConfidence'] })}>
              {CONFIDENCE_OPTIONS.map(([label, v]) => (
                <option key={label} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </section>

        <div className="row">
          <label className="check">
            <input type="checkbox" checked={showStops} onChange={(e) => setShowStops(e.target.checked)} />
            SEPTA stops
          </label>
          <label className="speed">
            Sort
            <select value={sortValue} onChange={(e) => set({ sort: e.target.value as Sort })}>
              {sorts.map(([label, v]) => (
                <option key={label} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button onClick={() => setFilters((f) => ({ ...DEFAULT_FILTERS, area: f.area }))} disabled={!isFiltered(filters) && !filters.q}>
            Reset
          </button>
        </div>
        {showStops && (
          <ul className="legend modes">
            {(Object.keys(MODE_COLORS) as (keyof typeof MODE_COLORS)[]).map((m) => (
              <li key={m}>
                <i style={{ background: css(MODE_COLORS[m]) }} />
                {m === 'tram' ? 'trolley' : m}
              </li>
            ))}
          </ul>
        )}

        <section className="results">
          <h2>
            {result ? `${result.total} of ${everything.length || '…'} places` : 'Loading…'}
            {loading && <span className="spin"> · updating</span>}
          </h2>
          {result && !items.length && <p className="muted">Nothing matches these filters.</p>}
          <ul className="list">
            {items.map((p) => (
              <li key={p.id}>
                <button
                  className={p.id === selectedId ? 'item on' : 'item'}
                  onClick={() => (p.id === selectedId ? setSelectedId(null) : flyTo(p))}
                  onMouseEnter={() => setHoverId(p.id)}
                  onMouseLeave={() => setHoverId(null)}
                >
                  <i style={{ background: css(kindColor(p.kind)) }} />
                  <span className="name">{title(p)}</span>
                  <em>
                    {p.kind}
                    {p.neighborhood ? ` · ${p.neighborhood}` : ''}
                  </em>
                  <span className="rail">{p.transit.nearest_rail_m !== null ? `rail ${metres(p.transit.nearest_rail_m)}` : 'no rail'}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <footer>
          {attribution.join(' · ')}
          {meta?.transit.service_date ? ` · Transit snapshot ${meta.transit.service_date}` : ''}
        </footer>
      </aside>
    </div>
  )
}
