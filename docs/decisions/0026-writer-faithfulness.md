# 0026: How faithful are the chat writer's summaries? (invented cases, rule checker, hand review)

- **Status:** Accepted as a measurement of the current writer on the dev half. **One split of two has been read; no fix has been tried.**
- **Date:** 2026-10-05
- **Code:** `chat_faithfulness.py` (case generator, checker, runner), `tests/test_chat_faithfulness.py` (9 tests of the instrument); design and rules in `docs/chat-eval/faithfulness/README.md`, run log and raw outputs in `docs/chat-eval/faithfulness/`
- Everything is invented and shareable. No Yelp data was used.
- **Reproduce:** `.venv/bin/python -m streetwalker.chat_faithfulness --split dev --save FILE` (about 15 minutes on the local model).

## Why

Decision 0025 left the writer's summaries unmeasured and showed one way they go wrong (a place credited with a patio it does not have). This measures it, without people, on cases where what every passage says is known by construction.

## How

A bank of 18 invented facts with three phrasings each; 60 cases of six types (present, absent, leak, polarity, standing, injection), ten each, from a fixed seed, split dev/test by index (30 each). The writer is called exactly as the chat calls it, with the search replaced by the known passages. A rule checker flags a summary that asserts a bank fact the place's passages lack, an invented number or name, praise for an aspect the passages fault, a contradiction of a top- or bottom-quarter standing, or planted text. The writer's `relevant` flag is compared with the construction and its quotes are tested for verbatim. The set, the rules and the checker were fixed before any model ran; a test checks that every passage contains only its own fact's words.

## Result (qwen2.5:7b, dev, writer prompt unchanged from 0025)

| | |
|---|---|
| Non-empty summaries | 46 of 65 places (the writer left the rest empty) |
| Rule-flagged | 5/46 |
| **After reading all 46 by hand** | **6/46 unfaithful (13%; 95% interval 6% to 26%)** |
| Quotes verbatim | 32/32 |
| `relevant` flag matches the construction | 53/65 |
| Planted instructions followed | 0/8 |

**What the faults are.** All six are the same thing: the question asks for something the place's passages do not say, and the writer builds an answer anyway. Four were **inference from a neighbouring fact**: "allows dogs, indicating it has takeout"; "open late, making it a potential option for takeout"; "a jazz trio ... suggesting it offers dessert". Two were an **unsupported negative recommendation**: "not recommended for families", with nothing about families in the passages. Where the place had the asked fact (`present`), or the passages were negative (`polarity`), or an instruction was planted (`injection`), there was no fault. Of 30 places that lacked the asked fact, 17 got a non-empty summary and 6 of those were faulty; the writer called 4 of them relevant, so the chat would have shown four of the six (the places it calls irrelevant are listed by name only, without their summary).

**The relevance flag errs in both directions.** Four false positives (the four speculations above) and eight false negatives. Most false negatives are a synonym the writer did not take ("Delivery was quick" for takeout, "worked on my laptop" for wifi for working) and a few are places with the right fact that it left out. A place with the asked fact that is called irrelevant is hidden from the answer's main list.

**Checker quality (hand review by an AI reader, not a person).** Of the 5 flags, 4 were correct and 1 was a false alarm (a summary that only restated a passage, flagged by the standings rule because "menu" is one of the food words). It missed 2 faults (the negative recommendations). So on this set precision was 4/5 and recall 4/6. The checker was not changed after seeing this, so the dev numbers stay comparable; the two weaknesses are known and should be fixed before the test split is read.

## What this does and does not show

- **Shows:** on simple invented passages, with a 7B local model, summaries stay faithful when the passages answer the question, and fail by speculating when they do not. The chat's quote check is not the issue here (all quotes were verbatim); a summary can be wrong in a way that no quote check can catch.
- **Does not show the rate on real reviews.** Real reviews are longer and messier; on the real reviews the same model produced many non-verbatim quotes (decision 0025), which these templated passages did not provoke. The 13% is a measurement of one failure mode on easy text, not an error rate for the product.
- **Small and one reader.** 46 summaries; the interval is wide. The hand review is mine, an AI, and the two disputed points (the ambiguous case, the false alarm) could be read differently.
- **A checker is not a judge.** It knows 18 facts; a fault outside the bank passes, as the two missed ones show.

## What follows

1. **Fix the checker first** (flag unsupported negative recommendations; tighten the standings rule so a summary that restates a passage is not flagged), judged by re-reading dev, **before** the test split is read.
2. **A writer v2** developed on dev only. Candidates: an explicit instruction that, when the passages do not mention what was asked, the place is not relevant and the summary must say the passages do not mention it, without inferring; and dropping summaries for places judged irrelevant. Judge it once on the held-out test split.
3. **Synonym misses in the relevance flag** are a separate problem (the retrieval already found these places); a v2 should be scored on false negatives too.
4. Until then the chat labels summaries "model-written, not checked", and this record gives the reader a measured reason.
