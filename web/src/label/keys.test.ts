import { describe, expect, it } from 'vitest'
import { ASPECTS, applyKey, complete, emptyDraft } from './keys'
import type { Draft } from './keys'

const press = (d: Draft, ...keys: string[]) => keys.reduce((acc, k) => applyKey(acc.draft, k), { draft: d } as ReturnType<typeof applyKey>)

describe('applyKey', () => {
  it('maps digits 1 to 5 onto levels 0 to 4 and moves to the next open row', () => {
    const { draft } = press(emptyDraft(), '1', '5')
    expect(draft.answers.food).toBe(0) // 1 is the most negative
    expect(draft.answers.atmosphere).toBe(4)
    expect(draft.active).toBe(2)
  })

  it('n means not mentioned, which is an answer and not a gap', () => {
    const { draft } = press(emptyDraft(), 'n')
    expect(draft.answers.food).toBeNull()
    expect(complete(draft.answers)).toBe(false)
  })

  it('submits only when all four aspects are answered', () => {
    expect(press(emptyDraft(), '3', 'n', '2', 'Enter').action).toBeUndefined() // three answered
    const done = press(emptyDraft(), '3', 'n', '2', '4', 'Enter')
    expect(done.action).toBe('submit')
    expect(complete(done.draft.answers)).toBe(true)
  })

  it('advances to the next open row, wraps round, and skips rows already answered', () => {
    let d = press(emptyDraft(), 'ArrowDown', 'ArrowDown', '4').draft // answer service first
    expect(d.answers.service).toBe(3)
    expect(d.active).toBe(3) // the next open row after service is value
    d = press(d, '1').draft // value answered; food and atmosphere are still open
    expect(d.answers.value).toBe(0)
    expect(d.active).toBe(0) // wraps round to food
    d = press(d, '2').draft
    expect(d.active).toBe(1) // atmosphere, not the answered service
    expect(d.answers.service).toBe(3) // never touched again
  })

  it('arrow keys and tab move between rows and wrap round', () => {
    expect(press(emptyDraft(), 'ArrowUp').draft.active).toBe(ASPECTS.length - 1)
    expect(press(emptyDraft(), 'Tab', 'Tab', 'Tab', 'Tab').draft.active).toBe(0)
  })

  it('backspace steps back within the item and u asks to undo the previous submission', () => {
    const d = press(emptyDraft(), '2', '3').draft // food and atmosphere answered, active is service
    const back = applyKey(d, 'Backspace').draft
    expect(back.answers.atmosphere).toBeUndefined()
    expect(back.answers.food).toBe(1)
    expect(applyKey(emptyDraft(), 'u').action).toBe('undo')
  })

  it('ignores keys it does not know, including 0 and 6 to 9, so a slip cannot record a wrong level', () => {
    for (const k of ['0', '6', '9', 'x', 'Shift']) {
      const { draft, action } = applyKey(emptyDraft(), k)
      expect(action).toBeUndefined()
      expect(draft).toEqual(emptyDraft())
    }
  })
})
