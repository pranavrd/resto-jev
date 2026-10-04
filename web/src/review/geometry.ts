/** GeoJSON in metres around the target building (x east, y north) -> SVG path data (y flipped: SVG grows downward). */

export interface GeoJson {
  type: string
  coordinates?: unknown
  geometries?: GeoJson[]
}

type Pt = [number, number]

const pt = ([x, y]: Pt) => `${x.toFixed(1)} ${(-y).toFixed(1)}`

const ring = (r: Pt[], close: boolean) => (r.length ? `M${r.map(pt).join('L')}${close ? 'Z' : ''}` : '')

/** One path string for any polygon or line geometry; empty for anything else, including empty collections. */
export function toPath(g: GeoJson | null | undefined): string {
  if (!g) return ''
  switch (g.type) {
    case 'Polygon':
      return (g.coordinates as Pt[][]).map((r) => ring(r, true)).join('')
    case 'MultiPolygon':
      return (g.coordinates as Pt[][][]).map((p) => p.map((r) => ring(r, true)).join('')).join('')
    case 'LineString':
      return ring(g.coordinates as Pt[], false)
    case 'MultiLineString':
      return (g.coordinates as Pt[][]).map((l) => ring(l, false)).join('')
    case 'GeometryCollection':
      return (g.geometries ?? []).map(toPath).join('')
    default:
      return ''
  }
}

/** Half-width in metres of the square view: wide enough for the target and the cameras, never tighter than minHalf. */
export function viewHalf(target: GeoJson, cameras: { x: number; y: number }[], minHalf = 30, maxHalf = 80): number {
  const flat = (toPath(target).match(/-?\d+\.?\d*/g) ?? []).map(Number)
  const reach = Math.max(0, ...flat.map(Math.abs), ...cameras.flatMap((c) => [Math.abs(c.x), Math.abs(c.y)]))
  return Math.min(maxHalf, Math.max(minHalf, reach * 1.35))
}
