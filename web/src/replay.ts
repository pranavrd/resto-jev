import type { LngLat, Step } from './types'

/** Index of the first element >= x in a sorted array (arr.length if none). */
export function lowerBound(arr: number[], x: number): number {
  let lo = 0
  let hi = arr.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (arr[mid] < x) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** How many elements of a sorted array are <= x. */
export function countThrough(sorted: number[], x: number): number {
  let lo = 0
  let hi = sorted.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (sorted[mid] <= x) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** Where the walker is at simulated time t. Steps must be sorted by t0. */
export function positionAt(steps: Step[], t: number): LngLat | null {
  if (steps.length === 0) return null
  const idx = countThrough(
    steps.map((s) => s.t0),
    t,
  )
  const step = steps[Math.max(0, idx - 1)]
  const p = step.p
  if (t <= step.t[0]) return p[0]
  if (t >= step.t[step.t.length - 1]) return p[p.length - 1]
  const k = Math.max(1, lowerBound(step.t, t))
  const span = step.t[k] - step.t[k - 1] || 1
  const f = (t - step.t[k - 1]) / span
  return [p[k - 1][0] + (p[k][0] - p[k - 1][0]) * f, p[k - 1][1] + (p[k][1] - p[k - 1][1]) * f]
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
