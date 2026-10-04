export type Sort = '' | 'relevance' | 'name' | 'transit'

export interface Filters {
  q: string
  area: string // '' = all areas
  kinds: string[]
  minConfidence: '' | 'medium' | 'high'
  source: '' | 'osm' | 'licence' | 'both'
  maxRailM: number | null
  minTrips: number | null
  sort: Sort
}

export const DEFAULT_FILTERS: Filters = {
  q: '',
  area: '',
  kinds: [],
  minConfidence: '',
  source: '',
  maxRailM: null,
  minTrips: null,
  sort: '',
}

export const MAX_LIMIT = 200 // the API's page cap; the census has fewer places than this

/** Query string for GET /places. Defaults are omitted, and a sort the API would reject is dropped. */
export function toParams(f: Filters): URLSearchParams {
  const p = new URLSearchParams()
  const q = f.q.trim()
  if (q) p.set('q', q)
  if (f.area) p.set('area', f.area)
  for (const k of f.kinds) p.append('kind', k)
  if (f.minConfidence) p.set('min_confidence', f.minConfidence)
  if (f.source) p.set('source', f.source)
  if (f.maxRailM !== null) p.set('max_rail_m', String(f.maxRailM))
  if (f.minTrips !== null) p.set('min_trips', String(f.minTrips))
  const sort = f.sort === 'relevance' && !q ? '' : f.sort // relevance ranks a text match, so it needs q
  if (sort) p.set('sort', sort)
  p.set('limit', String(MAX_LIMIT))
  return p
}

export function isFiltered(f: Filters): boolean {
  return JSON.stringify({ ...f, area: '', sort: '' }) !== JSON.stringify({ ...DEFAULT_FILTERS, area: '', sort: '' })
}

export function toggleKind(kinds: string[], kind: string): string[] {
  return kinds.includes(kind) ? kinds.filter((k) => k !== kind) : [...kinds, kind]
}
