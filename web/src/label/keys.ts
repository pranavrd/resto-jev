/** Keyboard logic of the aspect labelling page, kept apart from React so it can be tested. */

export const ASPECTS = ['food', 'atmosphere', 'service', 'value'] as const
export type Aspect = (typeof ASPECTS)[number]

/** undefined = not answered yet, null = not mentioned, 0 to 4 = how the reviewer feels, clearly negative to clearly positive. */
export type Answers = Record<Aspect, number | null | undefined>

export interface Draft {
  answers: Answers
  active: number // index into ASPECTS: the row the next key applies to
}

export type Outcome = { draft: Draft; action?: 'submit' | 'undo' }

export const emptyDraft = (): Draft => ({ answers: { food: undefined, atmosphere: undefined, service: undefined, value: undefined }, active: 0 })

export const complete = (a: Answers): a is Record<Aspect, number | null> => ASPECTS.every((k) => a[k] !== undefined)

const firstOpen = (a: Answers, from: number): number => {
  for (let step = 1; step <= ASPECTS.length; step++) {
    const i = (from + step) % ASPECTS.length
    if (a[ASPECTS[i]] === undefined) return i
  }
  return Math.min(from + 1, ASPECTS.length - 1)
}

/** What a key does. Digits 1 to 5 are levels 0 to 4 (so 1 is the most negative); n is "not mentioned". */
export function applyKey(d: Draft, key: string): Outcome {
  const aspect = ASPECTS[d.active]
  if (key >= '1' && key <= '5') {
    const answers = { ...d.answers, [aspect]: Number(key) - 1 }
    return { draft: { answers, active: firstOpen(answers, d.active) } }
  }
  if (key === 'n') {
    const answers = { ...d.answers, [aspect]: null }
    return { draft: { answers, active: firstOpen(answers, d.active) } }
  }
  if (key === 'Enter') return complete(d.answers) ? { draft: d, action: 'submit' } : { draft: d }
  if (key === 'u') return { draft: d, action: 'undo' }
  if (key === 'ArrowDown' || key === 'Tab') return { draft: { ...d, active: (d.active + 1) % ASPECTS.length } }
  if (key === 'ArrowUp') return { draft: { ...d, active: (d.active + ASPECTS.length - 1) % ASPECTS.length } }
  if (key === 'Backspace') {
    // step back: clear the active row's answer, or the previous row's if this one is still open
    const target = d.answers[aspect] !== undefined ? d.active : Math.max(0, d.active - 1)
    return { draft: { answers: { ...d.answers, [ASPECTS[target]]: undefined }, active: target } }
  }
  return { draft: d }
}

/** A click on a button in row `row`: answer that row (key '1' to '5' or 'n'), whichever row was active. Pure, so a click and the
 * keyboard go through the same code. */
export function choose(d: Draft, row: number, key: string): Draft {
  return applyKey({ ...d, active: row }, key).draft
}

/** A click on a row's background: make it the active row, keeping every answer. */
export function activate(d: Draft, row: number): Draft {
  return { ...d, active: row }
}
