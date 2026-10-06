# 0027: Checker c2 and writer w3 (a separate relevance check before the writer)

- **Status:** Accepted. w3 is the chat's default writer. It stops the speculation measured in decision 0026; it does **not** find more of the places that do answer a question.
- **Date:** 2026-10-05
- **Code:** `chat.py` (`VERIFY_*`, `verify_places`, `write_places`, `WRITE_VERSION = "w3"`), `chat_faithfulness.py` (checker c2, `--rescore`, `--writer`), 22 more tests; runs and log in `docs/chat-eval/faithfulness/`
- Everything measured here is invented and shareable. The one check on real reviews is in `docs/private/chat-sample-w3.md`.

## What changed

1. **Checker c2** (after hand-reading the first dev run of 0026): an unsupported negative recommendation ("not recommended for families", with nothing about it in the passages) is flagged; a sentence that restates a passage is not a standings contradiction. A test pins c2 to my hand labels on that run (it flags exactly the six faults and not the false alarm); c1 stays reproducible. **It was fitted to those dev labels**, and it still has a false alarm of its own (a negation more than five words before the fact word).
2. **Writer w3.** The writer no longer decides whether a place answers the question. A separate yes/no check does, **one passage at a time** (one yes makes the place relevant), with four worked examples that use no fact from the evaluation bank and no review id in the prompt. Only the places that pass go to the writer, whose own `relevant` flag is ignored; a place that passed but was left out of the writer's reply stays relevant without a summary. The prompt asks for no inference and no advice, and a place that does not pass has no summary at all.

## How it was developed (dev half only, so dev is spent)

| Step | Result on dev (shown summaries with a violation; relevance false positives / false negatives) |
|---|---|
| w1, the writer of 0025 | 4/28; 4 / 8 |
| w2: stricter wording | 2/30 (hand review: 3); 2 / 4 |
| w3, one check per place | 0/20; 0 / 10 (too strict) |
| w3, one check per passage | 0/20; 0 / 10 (same; a bug found on the way, fixed, same result) |
| w3, id removed and four examples added, chosen by running the check alone on dev places (id kept 15 true positives, id removed 16, plain quote 19, plus examples 21; false negatives 10, 9, 6, 4; false positives 0 throughout) | 0/26; 0 / 4 |

Along the way the check flipped its answer on the review id in the prompt (the same passage passed as "a", failed as "f60-0"), which is why the id is gone.

## The held-out test half, read once per system, criterion written first

Criterion (in `log.md` before the read): w3 is adopted only if its hand-reviewed shown unfaithful count is lower than w1's and its relevance errors are not higher.

| Test half (30 cases, 65 places) | w1 | w3 |
|---|---|---|
| Unfaithful summaries, every summary read by hand (an AI reader) | 4/44 (4% to 21%) | 0/21 (0% to 15%) |
| Of them shown to a user | 2/24 | 0/21 |
| Relevance errors (false positives, false negatives) | 12 (3, 9) | 9 (1, 8) |
| Recall of places that answer the question | 21/30 (70%) | 22/30 (73%) |
| Quotes verbatim | 31/31 | 26/26 |

Criterion met on both counts. **What it shows and does not:** the intervals overlap, so on 30 cases the rates are not statistically separated. The pattern is: the faults of w1 are the same on both halves (speculation on a question the passages do not answer, "not recommended" advice) and w3 produced none on either. Recall did not improve.

## What happens on the real reviews (five invented questions, private notes)

- **It does not speculate, and it misses real matches.** On "somewhere to sit outside for a drink in Rittenhouse" the check said no for all ten passages of five bars; w1 had found one. Reading those passages, most of them mention "outside" incidentally and the check was right to say no, but two were genuine ("a fabulous meal outside last weekend", "tables and chairs for my group outside") and were missed. So a user can be told "none of these clearly answers" when one does. That is the price of the precision.
- **A place that passes often gets no summary or quote.** The writer left several verified places out, and two of its quotes were dropped as not verbatim. The answer then shows the place with its standings only.
- **Filters-only questions** (the planner leaves the topic empty) return an alphabetical list of places with ratings, which reads like a recommendation. The answer now says so ("listed alphabetically: not a ranking, and not a recommendation"). A planner miss ("reservations for large groups" got no topic) is the cause of the worst case.
- **Speed.** An idle check call takes 1 to 2.5 s, and a question with passages makes about ten of them plus the plan and the writer. In the session, answers with passages took 98 to 372 s, a lot more than the 12 s of questions without passages, and those runs coincided with 8 to 10 GB of swap in use; I did not separate the memory effect from the extra calls. This is a real cost of w3.

## Limits

- **Small, invented, one reader.** 30 test cases of templated text, hand-reviewed by an AI. Real reviews are longer and messier, and nothing here is validated against people.
- **The checker is a checker.** 18 facts and word lists; c2 still has false alarms and cannot see a fault outside the bank.
- **The recall loss is unaddressed:** synonyms, rejected direct matches, and places whose passage carries a planted instruction (the check says no to those, which is safe and hides them).
- **The planner is unchanged** (67% fully correct, decision 0025) and a planner miss defeats everything after it.

## Not done

1. Improving the check's recall (a better model, a second look at the rejected places, or a lexical fallback when the retrieval score is high); a fresh invented set to judge it, since this test half is now read for both writers.
2. Cutting the cost: verifying all passages of a place in one call, and reusing the shared prompt prefix.
3. A planner v2, ascending sorts, multi-turn, a UI, and CI.
