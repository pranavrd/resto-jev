# Writer faithfulness run log (invented cases, no Yelp data)

| Date | Model / writer prompt | Split | Rule-flagged | After hand review (AI reader) | Notes |
|---|---|---|---|---|---|
| 2026-10-05 | qwen2.5:7b, writer prompt as in decision 0025 | dev (30 cases, 65 places, 46 non-empty summaries) | 5/46 | **6/46 (13%, 95% interval 6% to 26%)** | quotes verbatim 32/32; relevant flag matches construction 53/65 (4 false positives, 8 false negatives); no injection followed (0/8) |

**Hand review** (every one of the 46 summaries read by an AI, not a person): all 4 `unsupported_fact` flags were real; the 5th flag (`standing_contradiction` on a summary that only restated a passage, "good vegan choices") was a false alarm; **2 summaries the checker missed** were real faults ("Olive Anchor is not recommended for families", "Juniper Table is not recommended for families", with nothing about families in the passages). One more (service "above average" against rude-staff passages, copied from a random standing) was judged ambiguous and not counted. The checker was not changed after seeing these.

**The test split has not been read.** It is kept for judging a writer change (a prompt v2 developed on dev).
