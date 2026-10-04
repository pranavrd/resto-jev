import { describe, expect, it } from 'vitest'
import { distanceM, extent } from './geo'
import { topMode } from './kinds'
import { DEFAULT_FILTERS, isFiltered, toggleKind, toParams } from './query'

describe('toParams', () => {
  it('sends only the page limit for default filters', () => {
    expect(toParams(DEFAULT_FILTERS).toString()).toBe('limit=200')
  })

  it('repeats kind and maps each filter to the API name', () => {
    const p = toParams({
      ...DEFAULT_FILTERS,
      q: '  pizza ',
      area: 'rittenhouse',
      kinds: ['bar', 'cafe'],
      minConfidence: 'high',
      source: 'both',
      maxRailM: 400,
      minTrips: 1000,
      sort: 'transit',
    })
    expect(p.getAll('kind')).toEqual(['bar', 'cafe'])
    expect(Object.fromEntries(p)).toMatchObject({
      q: 'pizza',
      area: 'rittenhouse',
      min_confidence: 'high',
      source: 'both',
      max_rail_m: '400',
      min_trips: '1000',
      sort: 'transit',
    })
  })

  it('keeps a zero threshold, which means "must be at the stop"', () => {
    expect(toParams({ ...DEFAULT_FILTERS, minTrips: 0 }).get('min_trips')).toBe('0')
  })

  it('drops relevance sorting without text, which the API would reject', () => {
    expect(toParams({ ...DEFAULT_FILTERS, sort: 'relevance' }).has('sort')).toBe(false)
    expect(toParams({ ...DEFAULT_FILTERS, q: 'x', sort: 'relevance' }).get('sort')).toBe('relevance')
    expect(toParams({ ...DEFAULT_FILTERS, q: '   ', sort: 'relevance' }).has('sort')).toBe(false)
  })

  it('encodes user text instead of splicing it into the query', () => {
    const s = toParams({ ...DEFAULT_FILTERS, q: 'a&sort=distance' }).toString()
    expect(new URLSearchParams(s).get('q')).toBe('a&sort=distance')
    expect(new URLSearchParams(s).has('sort')).toBe(false)
  })
})

describe('filter state', () => {
  it('isFiltered ignores area and sort, which have their own controls', () => {
    expect(isFiltered({ ...DEFAULT_FILTERS, area: 'roxborough', sort: 'name' })).toBe(false)
    expect(isFiltered({ ...DEFAULT_FILTERS, kinds: ['bar'] })).toBe(true)
    expect(isFiltered({ ...DEFAULT_FILTERS, maxRailM: 200 })).toBe(true)
  })

  it('toggleKind adds and removes without mutating', () => {
    const a: string[] = ['bar']
    expect(toggleKind(a, 'cafe')).toEqual(['bar', 'cafe'])
    expect(toggleKind(a, 'bar')).toEqual([])
    expect(a).toEqual(['bar'])
  })
})

describe('geo', () => {
  it('measures distance in metres', () => {
    expect(distanceM([-75.17, 39.95], [-75.17, 39.95])).toBe(0)
    expect(distanceM([-75.17, 39.95], [-75.17, 39.951])).toBeCloseTo(111.2, 0)
    // 0.001 degrees of longitude is shorter by cos(latitude)
    expect(distanceM([-75.17, 39.95], [-75.169, 39.95])).toBeCloseTo(85.4, 0)
  })

  it('finds the extent, and null for no points', () => {
    expect(extent([])).toBeNull()
    expect(
      extent([
        [-75.2, 39.9],
        [-75.1, 40.0],
        [-75.15, 39.95],
      ]),
    ).toEqual([-75.2, 39.9, -75.1, 40.0])
  })

  it('colours a stop by its most rapid mode', () => {
    expect(topMode(['bus', 'subway'])).toBe('subway')
    expect(topMode(['bus', 'rail'])).toBe('rail')
    expect(topMode([])).toBe('bus')
  })
})
