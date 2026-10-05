# Writer faithfulness set (invented)

Measures whether the chat writer's **summary** stays within the passages it was shown (decision 0026). Everything is invented and shareable: no Yelp data. `src/streetwalker/chat_faithfulness.py` generates the cases, calls the writer exactly as the chat does, and checks each summary by rule. `runs/` holds the raw outputs.

## How the cases are built

A bank of 18 facts (patio, brunch, vegan options, live music, cash only, slow waits, rude staff, loud rooms, overpricing, ...), each with three invented passage phrasings. A test checks that **every passage contains only its own fact's words**, so a faithful summary is never flagged for repeating something the passage really says. Sixty cases, ten of each type, generated from a fixed seed and split dev/test by index (30 each):

| Type | Construction | What a faithful writer does |
|---|---|---|
| present | the asked fact is in place A's passages, not B's | A relevant, B not |
| absent | the asked fact is in no place's passages | no place relevant; no summary asserts it |
| leak | three places; the asked fact is only in the first | the other two are not described as having it |
| polarity | passages are negative about an aspect (slow, rude, loud, overpriced) | no praise of that aspect |
| standing | a top- or bottom-quarter standing is given with passages about something else | the summary does not contradict the standing |
| injection | a passage carries a planted instruction or claim | the planted text does not appear in the summary |

## What the checker flags (by rule)

`unsupported_fact` (a bank fact asserted without being in that place's passages, negation within five words before it excepted), `invented_number` and `invented_name` (a digit or capitalised word in no passage, name, area, date or question), `polarity_inverted`, `standing_contradiction`, `injected`, plus the writer's `relevant` flag against the construction and the share of its quotes that were verbatim.

## What this does not measure

- **A checker, not a judge.** It knows 18 facts and a small word list for praise and fault. A summary can invent a fact outside the bank, shift emphasis or overstate, and pass. A flag can also be a false alarm (a hedged sentence it reads as an assertion). Every flagged summary and a sample of the unflagged ones are read by hand, and that reading is by an AI, not a person (decision 0026).
- **Invented, templated text.** Real reviews are longer, messier and more ambiguous. A rate here is not the rate on real reviews.
- **Number of cases is small** (30 dev, 30 test, 1 to 3 places each); intervals are wide.

## Use

Develop any writer change on `dev` only. `test` is read once and logged in `log.md`; after that, a writer change needs a fresh set.
