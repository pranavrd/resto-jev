export type Rgb = [number, number, number]

export const KIND_COLORS: Record<string, Rgb> = {
  restaurant: [251, 146, 60],
  bar: [192, 132, 252],
  cafe: [45, 212, 191],
  'fast food': [250, 204, 21],
  'bakery or deli': [244, 114, 182],
  'ice cream': [125, 211, 252],
  'hotel or institution': [148, 163, 184],
  other: [203, 213, 225],
}
const FALLBACK: Rgb = [203, 213, 225]

export const kindColor = (kind: string): Rgb => KIND_COLORS[kind] ?? FALLBACK

export type StopMode = 'subway' | 'tram' | 'rail' | 'bus'
export const MODE_COLORS: Record<StopMode, Rgb> = {
  subway: [96, 165, 250],
  tram: [74, 222, 128],
  rail: [167, 139, 250],
  bus: [100, 116, 139],
}
const MODE_PRIORITY: StopMode[] = ['subway', 'tram', 'rail', 'bus']

/** The most rapid mode that serves a stop, which sets its colour. */
export function topMode(modes: string[]): StopMode {
  return MODE_PRIORITY.find((m) => modes.includes(m)) ?? 'bus'
}

export const css = (c: Rgb) => `rgb(${c[0]} ${c[1]} ${c[2]})`
