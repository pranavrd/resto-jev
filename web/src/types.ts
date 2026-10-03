export type LngLat = [number, number]

export interface Step {
  t0: number // simulated seconds at the start of the step
  t1: number
  r: number // 1 = a re-walk of a segment already walked
  j: number // 1 = the walker teleported to reach this step (new street-graph component)
  p: LngLat[]
  t: number[] // simulated seconds at each vertex of p
}

export interface Building {
  seq: number
  t: number // simulated seconds when the walker encounters it
  addr: string
  sig: 0 | 1 | 2 // evidence signal: 0 none, 1 OSM use tag or name, 2 linked business POI
  kinds: string
  lu: string // ground-truth land use label (development view only)
  text: string // the evidence text Jev will be shown
}

export interface Poly {
  b: number // index into buildings
  g: number[][][] // polygon rings
}

export interface AreaData {
  slug: string
  name: string
  profile: string
  bounds: [number, number, number, number]
  duration_s: number
  speed_ms: number
  streets: LngLat[][]
  steps: Step[]
  buildings: Building[]
  polys: Poly[]
  attribution: string
}

export interface IndexEntry {
  slug: string
  name: string
  profile: string
  buildings: number
  duration_s: number
}
