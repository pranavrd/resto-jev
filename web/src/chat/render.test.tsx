import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AnswerView, PendingView, PlaceCard } from './ChatApp'
import type { ChatResponse, Place } from './chat'

const hostile = '<script>alert(1)</script><img src=x onerror=alert(2)>'
const place = (over: Partial<Place> = {}): Place => ({
  id: 1, name: `Cafe ${hostile}`, kind: 'cafe', area: 'east_passyunk', relevant: true, summary: `Nice. ${hostile}`,
  quotes: [{ review_id: 'r1', date: '2021-06-01', quote: `loved it ${hostile}` }],
  standing: { food: { words: 'in the top quarter of rated places', n_mentions: 9 }, value: { words: 'below the median of rated places', n_mentions: 7 } }, ...over,
})
const response = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  status: 'provisional', banner: '', message: 'm', question: 'Cheap cafes in Roxborough', followup: true, searched_for: 'cafe, roxborough', caveat: 'These ratings are PROVISIONAL.',
  notice: '', alphabetical: false, in_scope: true, places: [place()], dropped: { quotes: 2, places: 0 }, models: {}, turn: { question: 'q', searched_for: 's', places: [] }, ...over,
})

describe('PlaceCard', () => {
  it('shows names, summaries and quotes as text, never as markup', () => {
    const html = renderToStaticMarkup(<PlaceCard place={place()} />)
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).toContain('east passyunk')
  })
  it('labels a model-written summary as unchecked, a quote as verbatim, and ratings as provisional', () => {
    const html = renderToStaticMarkup(<PlaceCard place={place()} />)
    expect(html).toContain('Model-written, not checked')
    expect(html).toContain('2021-06, verbatim')
    expect(html).toContain('aria-label="Provisional ratings"')
    expect(html).toContain('<b>food</b> in the top quarter of rated places')
  })
  it('omits the summary when the server sent none (quotes-only style) and says when there are no ratings', () => {
    const html = renderToStaticMarkup(<PlaceCard place={place({ summary: '', standing: {} })} />)
    expect(html).not.toContain('Model-written')
    expect(html).toContain('No ratings.')
  })
})

describe('AnswerView', () => {
  it('always ends with the provisional caveat the server sent', () => {
    expect(renderToStaticMarkup(<AnswerView r={response()} />)).toContain('These ratings are PROVISIONAL.')
    expect(renderToStaticMarkup(<AnswerView r={response({ places: [], notice: 'Nothing here.' })} />)).toContain('These ratings are PROVISIONAL.')
  })
  it('shows how a follow-up was understood and what was searched', () => {
    const html = renderToStaticMarkup(<AnswerView r={response()} />)
    expect(html).toContain('Understood as: <q>Cheap cafes in Roxborough</q>')
    expect(html).toContain('Searched for: cafe, roxborough.')
    expect(renderToStaticMarkup(<AnswerView r={response({ followup: false })} />)).not.toContain('Understood as')
  })
  it('lists the places the check did not accept apart, and reports dropped quotes', () => {
    const html = renderToStaticMarkup(<AnswerView r={response({ places: [place(), place({ id: 2, name: 'Other Cafe', relevant: false })] })} />)
    expect(html).toContain('Returned by the search but not judged to answer: Other Cafe.')
    expect(html).toContain('2 quotes the model offered were left out')
  })
  it('says the list is alphabetical, not a ranking, when the server says so', () => {
    expect(renderToStaticMarkup(<AnswerView r={response({ alphabetical: true })} />)).toContain('not a ranking, and not a recommendation')
    expect(renderToStaticMarkup(<AnswerView r={response()} />)).not.toContain('alphabetically')
  })
  it('shows a notice and no cards for an out-of-scope answer', () => {
    const html = renderToStaticMarkup(<AnswerView r={response({ places: [], followup: false, searched_for: '', notice: 'I can only answer questions about places.' })} />)
    expect(html).toContain('I can only answer questions about places.')
    expect(html).not.toContain('chat-place')
  })
})

describe('lowest-first answers', () => {
  it('say what the order is and that a low score is not a verdict', () => {
    const html = renderToStaticMarkup(<AnswerView r={response({ lowest_first: true })} />)
    expect(html).toContain('Lowest scores first')
    expect(html).toContain('not a verdict on the place')
    expect(renderToStaticMarkup(<AnswerView r={response()} />)).not.toContain('Lowest scores first')
  })
})

describe('PendingView', () => {
  it('shows what the server has said so far, and a Cancel button', () => {
    const html = renderToStaticMarkup(
      <PendingView progress={{ text: 'Checking place 2 of 5', searched_for: 'bar, rittenhouse', places: ['A', 'B'], followup: true, question: 'Bars in Rittenhouse' }} seconds="12 s" onCancel={() => {}} />,
    )
    expect(html).toContain('Understood as: <q>Bars in Rittenhouse</q>')
    expect(html).toContain('Searching for: bar, rittenhouse.')
    expect(html).toContain('Found: A, B.')
    expect(html).toContain('Checking place 2 of 5')
    expect(html).toContain('Cancel')
  })
  it('says it is starting before the first event, and renders server text as text', () => {
    expect(renderToStaticMarkup(<PendingView seconds="0 s" onCancel={() => {}} />)).toContain('Starting')
    const html = renderToStaticMarkup(<PendingView progress={{ text: 'x', places: [hostile], searched_for: hostile }} seconds="1 s" onCancel={() => {}} />)
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
  })
})

describe('strict matching', () => {
  it('is mentioned on an answer that used it and only then', () => {
    expect(renderToStaticMarkup(<AnswerView r={response({ models: { check: 'k2' } })} />)).toContain('Strict matching was on')
    expect(renderToStaticMarkup(<AnswerView r={response({ models: { check: 'k1' } })} />)).not.toContain('Strict matching')
  })
})
