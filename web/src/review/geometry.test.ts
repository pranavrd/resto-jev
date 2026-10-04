import { describe, expect, it } from 'vitest'
import { toPath, viewHalf } from './geometry'

describe('toPath', () => {
  it('flips y so north is up, and closes polygon rings', () => {
    const d = toPath({ type: 'Polygon', coordinates: [[[0, 0], [4, 0], [4, 2], [0, 0]]] })
    expect(d).toBe('M0.0 0.0L4.0 0.0L4.0 -2.0L0.0 0.0Z')
  })

  it('leaves lines open and handles multi-geometries and collections', () => {
    expect(toPath({ type: 'LineString', coordinates: [[0, 0], [1, 1]] })).toBe('M0.0 0.0L1.0 -1.0')
    const multi = toPath({ type: 'MultiLineString', coordinates: [[[0, 0], [1, 0]], [[2, 2], [3, 3]]] })
    expect(multi).toBe('M0.0 0.0L1.0 0.0M2.0 -2.0L3.0 -3.0')
    const coll = toPath({ type: 'GeometryCollection', geometries: [{ type: 'LineString', coordinates: [[0, 0], [1, 0]] }, { type: 'Point', coordinates: [0, 0] }] })
    expect(coll).toBe('M0.0 0.0L1.0 0.0')
  })

  it('returns an empty string for nothing, empty lines and unknown types', () => {
    expect(toPath(null)).toBe('')
    expect(toPath({ type: 'MultiLineString', coordinates: [] })).toBe('')
    expect(toPath({ type: 'Point', coordinates: [1, 2] })).toBe('')
  })
})

describe('viewHalf', () => {
  const target = { type: 'Polygon', coordinates: [[[-5, -3], [5, -3], [5, 3], [-5, -3]]] }
  it('never goes below the minimum or above the maximum', () => {
    expect(viewHalf(target, [])).toBe(30)
    expect(viewHalf(target, [{ x: 500, y: 0 }])).toBe(80)
  })
  it('grows to include a camera that stands off', () => {
    expect(viewHalf(target, [{ x: 40, y: -10 }])).toBeCloseTo(54, 5)
  })
})
