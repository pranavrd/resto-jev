export type LngLat = [number, number]

const EARTH_M = 6371008.8

/** Great-circle distance in metres. */
export function distanceM(a: LngLat, b: LngLat): number {
  const rad = Math.PI / 180
  const dLat = (b[1] - a[1]) * rad
  const dLng = (b[0] - a[0]) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** [west, south, east, north] of some points, or null when there are none. */
export function extent(points: LngLat[]): [number, number, number, number] | null {
  if (!points.length) return null
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const [lng, lat] of points) {
    w = Math.min(w, lng)
    e = Math.max(e, lng)
    s = Math.min(s, lat)
    n = Math.max(n, lat)
  }
  return [w, s, e, n]
}
