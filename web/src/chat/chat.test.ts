import { describe, expect, it } from 'vitest'
import { buildHistory, buildRequest, canSend, elapsed, errorText, MAX_HISTORY_SENT, MAX_QUESTION, splitPlaces } from './chat'
import type { ChatResponse, ChatTurn, Place } from './chat'

const response = (q: string): ChatResponse => ({
  status: 'provisional', banner: '', message: q, question: q, followup: false, searched_for: 's', caveat: 'c', notice: '', alphabetical: false, in_scope: true,
  places: [], dropped: { quotes: 0, places: 0 }, models: {}, turn: { question: q, searched_for: 's', places: ['A'] },
})
const turn = (id: number, state: ChatTurn['state'], q = `q${id}`): ChatTurn => ({ id, message: q, style: 'summary', state, startedAt: 0, response: state === 'done' ? response(q) : undefined })

describe('canSend', () => {
  it('needs some text and at most the server limit', () => {
    expect(canSend('   ')).toBe(false)
    expect(canSend('cafes')).toBe(true)
    expect(canSend('x'.repeat(MAX_QUESTION))).toBe(true)
    expect(canSend('x'.repeat(MAX_QUESTION + 1))).toBe(false)
  })
})

describe('buildHistory', () => {
  it('sends only completed turns, as the server described them, oldest first', () => {
    const h = buildHistory([turn(1, 'done'), turn(2, 'error'), turn(3, 'pending'), turn(4, 'done')])
    expect(h.map((t) => t.question)).toEqual(['q1', 'q4'])
    expect(h[0]).toEqual({ question: 'q1', searched_for: 's', places: ['A'] })
  })
  it('keeps the most recent turns when there are many', () => {
    const many = Array.from({ length: 9 }, (_, i) => turn(i, 'done'))
    const h = buildHistory(many)
    expect(h).toHaveLength(MAX_HISTORY_SENT)
    expect(h[h.length - 1].question).toBe('q8')
    expect(h[0].question).toBe('q3')
  })
  it('is empty for a new chat', () => expect(buildHistory([])).toEqual([]))
})

describe('buildRequest', () => {
  it('trims the message, passes the style through and attaches the history', () => {
    expect(buildRequest('  cheap eats  ', 'quotes', [turn(1, 'done')])).toEqual({
      question: 'cheap eats',
      style: 'quotes',
      history: [{ question: 'q1', searched_for: 's', places: ['A'] }],
    })
  })
})

describe('errorText', () => {
  it('names the flag when the router is off', () => expect(errorText(404)).toContain('STREETWALKER_TABLEMAP=1'))
  it('uses the server detail for model problems', () => {
    expect(errorText(503, 'chat model down. Use mode=lexical')).toContain('chat model down')
    expect(errorText(502, 'the model did not return JSON; try rephrasing')).toContain('try rephrasing')
  })
  it('reads a gateway error with no detail as an unreachable API, not as a model problem', () => {
    for (const status of [502, 503, 504]) expect(errorText(status)).toContain('Cannot reach the API')
  })
  it('handles an unreachable API, validation errors and anything else', () => {
    expect(errorText(null)).toContain('Cannot reach')
    expect(errorText(422)).toContain('not accepted')
    expect(errorText(500)).toBe('The request failed (500).')
  })
})

describe('elapsed and splitPlaces', () => {
  it('formats seconds and minutes', () => {
    expect(elapsed(4400)).toBe('4 s')
    expect(elapsed(61_000)).toBe('1 min 1 s')
    expect(elapsed(-5)).toBe('0 s')
  })
  it('separates the places the check accepted from the others', () => {
    const p = (id: number, relevant: boolean): Place => ({ id, name: `P${id}`, kind: 'bar', area: 'x', relevant, summary: '', quotes: [], standing: {} })
    const { shown, other } = splitPlaces([p(1, true), p(2, false), p(3, true)])
    expect(shown.map((x) => x.id)).toEqual([1, 3])
    expect(other.map((x) => x.id)).toEqual([2])
  })
})
