# Writer faithfulness run log (invented cases, no Yelp data)

| Date | Model / writer prompt | Split | Rule-flagged | After hand review (AI reader) | Notes |
|---|---|---|---|---|---|
| 2026-10-05 | qwen2.5:7b, writer prompt as in decision 0025 | dev (30 cases, 65 places, 46 non-empty summaries) | 5/46 | **6/46 (13%, 95% interval 6% to 26%)** | quotes verbatim 32/32; relevant flag matches construction 53/65 (4 false positives, 8 false negatives); no injection followed (0/8) |

**Hand review** (every one of the 46 summaries read by an AI, not a person): all 4 `unsupported_fact` flags were real; the 5th flag (`standing_contradiction` on a summary that only restated a passage, "good vegan choices") was a false alarm; **2 summaries the checker missed** were real faults ("Olive Anchor is not recommended for families", "Juniper Table is not recommended for families", with nothing about families in the passages). One more (service "above average" against rude-staff passages, copied from a random standing) was judged ambiguous and not counted. The checker was not changed after seeing these.

**The test split has not been read.** It is kept for judging a writer change (a prompt v2 developed on dev).

## Writer v2/v3 development (dev half only), 2026-10-05

Checker c2 (two changes made after hand-reading the first dev run: unsupported negative recommendations are flagged; a sentence that restates a passage is not a standings contradiction). On the first dev run it flags exactly the six hand-judged faults and nothing else (a test pins this). **It was fitted to those dev labels**, so any further reading is by hand again.

| Step | Change | Dev result (shown summaries with a violation / relevance FP, FN) |
|---|---|---|
| w1 (baseline) | prompt of decision 0025, checker c2 | 4/28 shown; FP 4, FN 8 |
| iter 1, w2 | stricter prompt: related facts do not count, no inference, no advice, irrelevant places get no summary, one worked example with facts outside the bank | 2/30 shown flagged (hand review: 3 faults incl. one "implying free wifi" the checker missed); FP 2, FN 4 |
| iter 2, w3 | relevance moved out of the writer into a separate yes/no check, one call per place, and the writer sees only places that passed | 0/20 shown; FP 0, FN 10 (too strict) |
| iter 3, w3 | the check is made one passage at a time, any yes counts | same: 0/20; FP 0, FN 10. A bug found while looking: a place that passed the check but was left out of the writer's reply was counted irrelevant (fixed; re-run gave the same result) |
| iter 4, w3 | the check's input format: the answer flipped on the review id in the prompt, so the id is removed and four worked examples are added (none from the bank). Chosen by running the check alone on dev places: id kept 15 TP / 10 FN / 0 FP; id removed 16/9/0; plain quote, question last 19/6/0; plus looser wording 20/5/0; plus four examples **21/4/0** | see "final dev run" below |

Four dev iterations in all, so dev is no longer an estimate of anything for w3: it was used to build it.

### Adoption criterion, written before the test split is read

The test half is read **once for w1 and once for w3** (the same 30 cases, each system once). w3 becomes the chat's default writer only if, on test, (a) its hand-reviewed count of shown summaries with an unfaithful statement is lower than w1's, and (b) its relevance errors (false positives plus false negatives) are not higher than w1's. Otherwise w1 stays the default and the result is reported as it is. Both flagged and unflagged summaries are read by hand, by an AI reader, as for the first dev run.

### Final dev run, writer w3 as it ships (tuned on dev: not an estimate)

0 of 26 shown summaries flagged; relevance 61/65 (false positives 0, false negatives 4); quotes verbatim 31/31.

### Held-out test half, read once per system (2026-10-05)

| | w1 (baseline, decision 0025) | w3 (verifier + writer) |
|---|---|---|
| Non-empty summaries | 44 | 21 |
| Rule-flagged (checker c2) | 5 | 1 |
| **Unfaithful after reading every summary by hand (AI reader)** | **4/44** (9%; 95% interval 4% to 21%) | **0/21** (0%; 0% to 15%) |
| Of them, shown to a user (writer called the place relevant) | 2/24 | 0/21 |
| Relevance errors (false positives, false negatives) | 12 (3, 9) | 9 (1, 8) |
| Recall of the places that do answer the question | 21/30 (70%; 52% to 83%) | 22/30 (73%; 56% to 86%) |
| Quotes verbatim | 31/31 | 26/26 |

**What the hand review found.** w1: the two speculations that were shown (a takeout claim "as evidenced by gluten-free pasta and free wifi"; "a bakery or deli, suggesting they likely have desserts"), two "not recommended for brunch" statements on places judged irrelevant, and one rule flag that was a false alarm (a negated sentence whose negation sat six words before the fact word). w3: its one rule flag (`polarity_inverted`) was a false alarm too: the summary reports the given standing ("above the median") next to the negative passages ("despite the high prices"), the same ambiguous kind that was not counted on dev. No fault was found in the other 20.

**Criterion, as written before the read:** (a) w3's shown unfaithful count is lower than w1's: 0 against 2, met; (b) w3's relevance errors are not higher: 9 against 12, met. **w3 is adopted as the default writer (decision 0027).**

**How much this shows.** The interval on 0/21 against 4/44 (or 2/24 shown) overlaps: on 30 test cases the difference in rate is not statistically established. What is consistent is the pattern: on both halves the faults of w1 are the same speculation on questions the passages do not answer, and w3 produced none of them on either half. **Recall did not improve** (70% against 73%): the check still misses about a quarter of the places that do answer, mostly synonyms ("a band on Saturday" for live music, "worked on my laptop" for wifi), a few direct matches it rejected, and places whose passage carried a planted instruction (it says no to those, which hides them).
