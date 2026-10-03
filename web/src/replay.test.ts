import { describe, expect, it } from 'vitest'
import { countThrough, formatClock, lowerBound, positionAt } from './replay'
import type { Step } from './types'

const step = (t0: number, t1: number, p: [number, number][], j = 0): Step => ({
  t0,
  t1,
  r: 0,
  j,
  p,
  t: p.map((_, i) => t0 + ((t1 - t0) * i) / (p.length - 1)),
})

describe('binary searches', () => {
  it('lowerBound finds the first element >= x', () => {
    expect(lowerBound([1, 3, 5], 0)).toBe(0)
    expect(lowerBound([1, 3, 5], 3)).toBe(1)
    expect(lowerBound([1, 3, 5], 4)).toBe(2)
    expect(lowerBound([1, 3, 5], 9)).toBe(3)
  })
  it('countThrough counts elements <= x', () => {
    expect(countThrough([1, 3, 3, 5], 0)).toBe(0)
    expect(countThrough([1, 3, 3, 5], 3)).toBe(3)
    expect(countThrough([1, 3, 3, 5], 99)).toBe(4)
  })
})

describe('positionAt', () => {
  const steps = [
    step(0, 10, [[0, 0], [10, 0]]),
    step(10, 20, [[10, 0], [10, 10]]),
    step(20, 30, [[50, 50], [60, 50]], 1), // after a jump
  ]
  it('interpolates within a step', () => {
    expect(positionAt(steps, 5)).toEqual([5, 0])
    expect(positionAt(steps, 15)).toEqual([10, 5])
  })
  it('is continuous at step boundaries and jumps where the walker teleports', () => {
    expect(positionAt(steps, 10)).toEqual([10, 0])
    expect(positionAt(steps, 20)).toEqual([50, 50])
  })
  it('clamps before the start and after the end', () => {
    expect(positionAt(steps, -5)).toEqual([0, 0])
    expect(positionAt(steps, 999)).toEqual([60, 50])
  })
  it('returns null with no steps', () => {
    expect(positionAt([], 1)).toBeNull()
  })
})

describe('formatClock', () => {
  it('formats h:mm:ss', () => {
    expect(formatClock(0)).toBe('0:00:00')
    expect(formatClock(3725)).toBe('1:02:05')
    expect(formatClock(-3)).toBe('0:00:00')
  })
})
