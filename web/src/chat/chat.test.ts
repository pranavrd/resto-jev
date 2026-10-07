import { describe, expect, it } from 'vitest'
import {
  applyStage, buildHistory, buildRequest, canSend, elapsed, errorText, loadChat, MAX_HISTORY_SENT, MAX_QUESTION, MAX_SAVED_TURNS, parseStream, saveChat, SEARCH_ERROR, settle, splitPlaces, STORAGE_KEY,
} from './chat'
import type { ChatResponse, ChatTurn, Place, StreamEvent } from './chat'

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
      strict: false,
      history: [{ question: 'q1', searched_for: 's', places: ['A'] }],
    })
    expect(buildRequest('x', 'summary', [], true).strict).toBe(true)
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

describe('parseStream', () => {
  it('returns complete events and keeps an unfinished line for the next chunk', () => {
    const a = parseStream('{"event":"stage","stage":"plan"}\n{"event":"stage","stage":"se')
    expect(a.events).toHaveLength(1)
    expect(a.rest).toBe('{"event":"stage","stage":"se')
    const b = parseStream(a.rest + 'arch"}\n\n{"event":"cancelled"}\n')
    expect(b.events.map((e) => e.event)).toEqual(['stage', 'cancelled'])
    expect(b.rest).toBe('')
  })
  it('skips blank keep-alive lines and anything that is not an event', () => {
    expect(parseStream('\n\nnot json\n{"x":1}\n[1]\n"s"\n').events).toEqual([])
  })
})

describe('applyStage', () => {
  type Stage = Extract<StreamEvent, { event: 'stage' }>
  const st = (o: Partial<Stage>): Stage => ({ event: 'stage', stage: 'plan', ...o })
  it('keeps what earlier stages said and replaces the text', () => {
    let p = applyStage(undefined, st({ text: 'Working out what to search for' }))
    p = applyStage(p, st({ stage: 'search', text: 'Searching', searched_for: 'bar, rittenhouse', question: 'Bars in Rittenhouse', followup: true }))
    p = applyStage(p, st({ stage: 'found', text: 'Found 2 places', places: ['A', 'B'] }))
    expect(p).toMatchObject({ text: 'Found 2 places', searched_for: 'bar, rittenhouse', question: 'Bars in Rittenhouse', followup: true, places: ['A', 'B'] })
  })
  it('counts the check from one and never past the total, and clears the count when writing starts', () => {
    let p = applyStage(undefined, st({ stage: 'check', done: 0, total: 5 }))
    expect(p.text).toBe('Checking place 1 of 5')
    p = applyStage(p, st({ stage: 'check', done: 7, total: 5 }))
    expect(p.text).toBe('Checking place 5 of 5')
    p = applyStage(p, st({ stage: 'write', text: 'Writing the summaries' }))
    expect(p).toMatchObject({ text: 'Writing the summaries', done: undefined, total: undefined })
  })
})

describe('settle', () => {
  it('takes the answer, the server error with the same wording as before, or says what happened', () => {
    expect(settle({ event: 'answer', data: response('q') })).toMatchObject({ state: 'done' })
    expect(settle({ event: 'error', status: 503, detail: 'chat model down' })).toEqual({ state: 'error', error: 'chat model down' })
    expect(settle({ event: 'cancelled' })).toEqual({ state: 'error', error: 'Cancelled.' })
    expect(settle(undefined)).toEqual({ state: 'error', error: SEARCH_ERROR }) // the stream ended with no answer: the server died
  })
})

describe('saving and loading the conversation', () => {
  const fake = () => {
    const m = new Map<string, string>()
    return { m, getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) }
  }
  it('saves only finished turns, without their progress, and loads them back with the style', () => {
    const s = fake()
    saveChat(s, 'quotes', [turn(1, 'done'), turn(2, 'error'), { ...turn(3, 'pending'), progress: { text: 'x' } }], true)
    expect(loadChat(s)).toEqual({ style: 'quotes', strict: true, turns: [turn(1, 'done')] })
    expect(s.m.get(STORAGE_KEY)).not.toContain('progress')
  })
  it('keeps the newest turns only, and clears the store when nothing is left (New chat)', () => {
    const s = fake()
    saveChat(s, 'summary', Array.from({ length: MAX_SAVED_TURNS + 5 }, (_, i) => turn(i, 'done')))
    const back = loadChat(s).turns
    expect(back).toHaveLength(MAX_SAVED_TURNS)
    expect(back[back.length - 1].id).toBe(MAX_SAVED_TURNS + 4)
    saveChat(s, 'summary', [])
    expect(s.m.has(STORAGE_KEY)).toBe(false)
  })
  it('starts empty from a missing, corrupt, foreign or hand-edited entry, and never throws', () => {
    const s = fake()
    expect(loadChat(s).turns).toEqual([])
    for (const bad of ['{', 'null', '[]', '{"v":2,"turns":[]}', '{"v":1,"turns":"x"}', '{"v":1,"style":"poem","turns":[{"id":1},{"id":"a","state":"done"},null]}']) {
      s.m.set(STORAGE_KEY, bad)
      expect(loadChat(s)).toEqual({ style: 'summary', strict: false, turns: [] })
    }
    expect(loadChat(null)).toEqual({ style: 'summary', strict: false, turns: [] })
    expect(() => saveChat(null, 'summary', [turn(1, 'done')])).not.toThrow()
    const full = { ...fake(), setItem: () => { throw new Error('quota') } }
    expect(() => saveChat(full, 'summary', [turn(1, 'done')])).not.toThrow()
    const broken = { getItem: () => { throw new Error('blocked') }, setItem: () => {}, removeItem: () => {} }
    expect(loadChat(broken).turns).toEqual([])
  })
})
