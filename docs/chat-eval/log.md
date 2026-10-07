# Chat planner evaluation log (invented questions, no Yelp data)

Set written before any model ran on it (`plan_questions.json`, rules in README.md). Plans are scored per field and as "fully correct" (every scored field right).

| Date | Model | Split | Prompt | Fully correct | Notes |
|---|---|---|---|---|---|
| 2026-10-05 | qwen2.5:7b | dev | first draft | 17/24 | in_scope 24/24; misses: topic left empty for a dish or occasion, one area forced onto a two-area comparison, "drinks" not treated as food |
| 2026-10-05 | qwen2.5:7b | dev | revised once on dev (three generic rules added) | 21/24 | **tuned on dev, so not an estimate** |
| 2026-10-05 | qwen2.5:7b | **test** | revised, frozen | **16/24** | read once. in_scope 23/24, area 20/20, near_rail 20/20, kinds 10/10, aspects 16-20/20 (food worst: sets "good" for a dish, "Sushi", "Thai food"), topic 8/13 (empty for "open late", "groups", "watching sports"), sort 3/3. One false out-of-scope ("Dog friendly places") |
| 2026-10-05 | gemma2:9b | dev | revised | not scored | the first request returned text that was not valid JSON under the few-shot chat format, so the run stopped; not investigated, since the owner chose qwen2.5:7b |

The test split has now been read for this prompt. A change to the planner prompt needs a fresh invented set to be judged on; do not tune on this one again.


## Planner p2 (decision 0029), 2026-10-05

Fresh set v2 (`plan_questions_v2.json`, 32 dev + 32 test, written before any planner-v2 run). **Scorer v2:** the first scorer marked a topic wrong whenever it equalled the question; that penalised correct plans for questions that are only a topic ("Sushi", "dog friendly patios"). It now applies only to questions of more than six words. It changes p1's earlier test count by nothing ("Sushi" also had a wrong food level), but it is a change to the instrument after seeing results and is noted here.

| Run | Fully correct |
|---|---|
| p1 on v2 dev | 18/32 |
| p2, first draft (new prompt and examples, three guards on aspects and topic) on v2 dev | 23/32 (24/32 under scorer v2; the run predates the scorer fix) |
| p2, second version (the model decides scope and topic; kinds, area, rail, aspect levels and sort are read off the question by rule) on v2 dev | 32/32 |

**The 32/32 is not an estimate**: the rules were written from the dev misses. A second caution: the word lists (quality words, kinds, rail words) were written with the whole v2 set in view, test half included ("friendliest", "outstanding", "outstanding" among them), so the v2 test half is **not fully blind for the vocabulary**.

### Frozen, and what will judge it

Planner p2 is frozen (sha256 of the planner code and prompts, `chat.py` from `PLAN_SCHEMA` to the search step: `498c0a12e448c13e`). A **third set, v3** (`plan_questions_v3.json`, 32 questions in natural wording, some deliberately outside the word lists) is written **after** this freeze and read once for p1 and once for p2, together with the v2 test half. 

**Criterion, written before any of these reads:** p2 becomes the chat's default planner if, on v3, (a) its fully-correct plans exceed p1's by at least 5 of 32, and (b) its in-scope errors are not more than p1's. The v2 test half is reported as well but, for the vocabulary reason above, does not decide.

### Reads after the freeze (2026-10-05, qwen2.5:7b)

| Set | p1 fully correct | p2 fully correct | Note |
|---|---|---|---|
| **v3** (32, written after the freeze, decides) | **19/32** | **29/32** | p2 right and p1 wrong on 13, p1 right and p2 wrong on 3 (exact sign test p = 0.02); scope errors p1 2, p2 0 |
| v2 test (32) | 20/32 | 32/32 | not blind for the vocabulary (the word lists were written with this half in view) |
| v1 test (24) | 16/24 (recorded in decision 0025) | 23/24 | the v1 misses were known when p2 was designed |
| v1 dev (24) | 21/24 | 24/24 | likewise |

**Criterion as written before the reads, on v3:** (a) p2 exceeds p1 by at least 5 of 32: +10, met; (b) p2's in-scope errors are not more than p1's: 0 against 2, met. **p2 is adopted as the default planner (decision 0029).**

p2's three misses on v3, left as they are: "Terrific staff and a fun vibe" (a quality word outside the lists, so the service level is dropped), "a coffee shop near the Broad Street Line" (no rail word, so near-rail is false and the topic becomes the line's name), and "the three best bars" (the topic becomes "three"). Median time per plan: 7.2 s for p2 against 4.3 s for p1 (a longer prompt).


## Multi-turn follow-ups (decision 0031), 2026-10-05

Set `followups_v1.json` (16 dev + 16 test conversations, written before the rewrite existed). The rewrite turns a follow-up message into a standalone question with the earlier turns as context (qwen2.5:7b), a guard discards a rewrite that drops a word the user wrote, and planner p2 plans the result.

| Run (dev) | Rewrite + plan, plan and flag right | Plan right with history | Plan right without history (baseline) | Controls unchanged |
|---|---|---|---|---|
| first draft | 12/16 | 13/16 | 9/16 | 4/4 |
| rules added to the prompt (a reference to a set keeps the earlier search, "and X" replaces, one named place is asked about alone, an added condition is a follow-up) and four worked examples | 14/16 | 15/16 | 9/16 | 4/4 |

Two dev misses remain ("and bakeries?" is rewritten as "Cafes and bakeries", and "not too loud though" is not seen as a follow-up) even though the prompt now carries a near-identical example for each; tuning stops here. **Dev is spent; the 14/16 is not an estimate.**

### Frozen, and what will judge it

The rewrite code and prompt are frozen (sha256 of `chat.py` from `MAX_HISTORY` to the `Answer` class: `ccf7e04760cfd8b8`). The test half (16 conversations) is read **once**, for the rewrite and for the no-history baseline together. **Criterion, written before the read:** (a) the plan is right with history on at least 5 more of 16 than without; (b) the follow-up flag is acceptable on at least 14 of 16; (c) all four controls come back unchanged. If any fails the multi-turn rewrite ships as an option that the record says is not validated, or does not ship.

### Held-out read (2026-10-05, qwen2.5:7b, planner p2), once

| 16 test conversations | Rewrite + plan |
|---|---|
| Plan right **with history** | **14/16** |
| Plan right **without history** (the bare message) | **7/16** |
| Follow-up flag acceptable | 15/16 |
| Controls (not follow-ups) returned unchanged | 4/4 |
| Plan and flag both right | 14/16 |

**Criterion as written before the read:** (a) at least +5 of 16 over the baseline: **+7, met**; (b) flag acceptable on at least 14 of 16: **15, met**; (c) all four controls unchanged: **4/4, met.** The rewrite ships.

The two test misses: "and good service as well" was not recognised as a follow-up (the same weakness as the dev miss "not too loud though": a message that only adds a condition with "and", "also" or "though"), and in "any with outdoor seating?" the rewrite kept the earlier topic ("craft beer bars with outdoor seating") so the topic the planner chose was not the one expected. Both are left as limits.


## Follow-up rewrite r2 (decision 0032), 2026-10-06

**Set `followups_v2.json`:** 32 conversations (16 dev, 16 test) written **before** r2 was built or run, to cover what `followups_v1` did not: a message that only adds a condition ("and good service as well", "not too loud though"), conversations with two and three earlier turns, a subject that changes mid-conversation, and four controls per half. Same fields and scorer as v1.

**First, a diagnosis that corrects decision 0031.** Both misses that 0031 called "the model does not recognise an add-a-condition message as a follow-up" were not the model's. The raw reply for both was `followup: true` with a correct standalone question ("Quiet cafes in Rittenhouse with good service"). The code guard `kept_the_words` threw it away because the user's message contained "well" and "though", which the guard counted as content words the rewrite had dropped. Decision 0031 had the cause wrong.

**Baseline, r1 (the rewrite of decision 0031) on v2 dev:** 12/16 fully correct (plan right with history 12/16, without history 4/16, flag acceptable 14/16, controls 4/4). Misses: the two add-a-condition messages above (the guard), and a three-turn-deep case where the rewrite took the area from the older of two turns (the model was not told which turn is current).

**What r2 changes:** (1) the guard exempts connectives ("well", "though", "plus", "but", "maybe", "perhaps", "actually", "anyway", "however", "although", "otherwise", "please"); (2) the history labels the last turn "Latest turn" (older ones "Earlier turn") and the prompt says the latest turn is the current search and area and kind come from it; (3) the prompt names the add-a-condition case as a follow-up, with three new worked examples whose sentences are not in either set. Nothing about the test half was looked at.

| Run | Fully correct | Plan with history | Baseline (no history) | Flag ok | Controls |
|---|---|---|---|---|---|
| r1, v2 dev | 12/16 | 12/16 | 4/16 | 14/16 | 4/4 |
| **r2, v2 dev (first and only iteration)** | **15/16** | 15/16 | 4/16 | 16/16 | 4/4 |
| r1, v1 dev (spent; regression only) | 14/16 | | 9/16 | | 4/4 |
| r2, v1 dev (spent; regression only) | 15/16 | 15/16 | 9/16 | 16/16 | 4/4 |

The one dev miss for r2 on v2 is a control whose plan has a topic that should be empty (a planner issue, the same in the baseline). **Dev is spent for r2: the 15/16 is not an estimate, and r2's guard exemptions were chosen by looking at the dev failures.**

### Frozen, and what will judge it

r2 code and prompt are frozen (sha256 of `chat.py` from the multi-turn heading to the `Answer` class: `3f59c0bc1e6126c7`). The v2 test half (16 conversations) is read **once for r1 and once for r2**. **Criterion, written before the read:** (a) r2 is fully correct on at least 3 more of 16 than r1; (b) all four controls come back unchanged; (c) the follow-up flag is acceptable on at least as many as for r1. If any fails, r2 is not made the default and the record says so.

### Held-out read (2026-10-06, qwen2.5:7b, planner p2), once for each

| 16 test conversations | r1 | r2 |
|---|---|---|
| Fully correct (plan and flag) | 14/16 | **16/16** |
| Plan right with history | 14/16 | 16/16 |
| Plan right without history (bare message) | 5/16 | 5/16 |
| Follow-up flag acceptable | 14/16 | 16/16 |
| Controls returned unchanged | 4/4 | 4/4 |
| add-a-condition on an aspect (4) | 2/4 | 4/4 |
| add-a-condition on a topic (4), chains (2), change (1), reference (1) | 8/8 | 8/8 |

**Criterion as written before the read:** (a) at least 3 more of 16 than r1: **+2, NOT met.** (b) controls unchanged: 4/4, met. (c) flag at least as often right as r1: 16 against 14, met.

**The criterion was badly set.** r1 scored 14/16 on this half, so "+3" could never be reached (the ceiling was +2). I should have seen that r1's dev score (12/16) left no room for +3 on a half it might do better on. It is reported as not met, not re-read as met. **Adoption is a judgement that overrides the written rule,** made in decision 0032, on this evidence: the two r1 misses were exactly the guard rejecting a correct rewrite ("plus great service", "... as well"), r2 fixed both, nothing that r1 got right got wrong, and the controls held. What the held-out read does **not** show: any benefit of the "Latest turn" labelling (the chain cases were 2/2 under r1 too; its benefit is seen only on the dev chain case), and anything beyond 32 invented conversations by one author.


## Planner p3 (decision 0032), 2026-10-06

**Why.** Decision 0029 left three known misses on its third set ("terrific staff", "Broad Street Line", "the three best bars"), and said the word lists were short and English. p3 widens them in general English rather than by patching those three questions.

**Set `plan_questions_v4.json`:** 48 questions (24 dev, 24 test) written before p3 was built, in the categories of those misses (quality words outside the lists, nouns for the people who work in a place, transit lines named without a rail word, number words, kinds of place, price phrasings, and out-of-scope questions). p2 on v4 dev: **7/24 fully correct.**

**v4 is development data, all of it.** I wrote both halves knowing the categories, and then added to the lists words that are in the v4 *test* half ("marvelous", "magnificent", "brewpub", "sandwich shop", "PATCO"), so the test half is not held out for p3. p3 on v4: **dev 24/24, test 23/24** (the miss: "Bars where the people working are kind", no aspect word in the question). Those numbers are not an estimate of anything.

**What p3 changes** (p2's lists stay available and a test compares them: 750 plans from 250 questions are identical under p2 before and after the refactor): (1) quality adjectives, nouns for the people who work in a place (crew, team, waitstaff), "reasonably priced"-type phrases, an adjective right after an aspect noun ("the crew friendliest"), hyphenated compounds read as one word ("top-notch"); (2) kinds of place (gastropub, brewpub, lounge, coffeehouse, patisserie, creamery, sandwich shop) and "coffee bar" as a cafe, not a bar; (3) transit lines named without a rail word (Broad Street Line, Market-Frankford, the El, Orange or Blue Line) set `near_rail` and are not a topic; (4) number words are not a topic ("three best bars", "a couple of"); (5) the model's topic loses the quality, kind, area, rail and number words that the residual also drops ("stellar service" becomes empty); (6) the prompt says a question naming a transit line is in scope ("Restaurants near the Orange Line" had been called out of scope). Median plan time is unchanged by the code; the longer prompt is the same one-line change.

### Frozen, and the set that will judge it

p3 is frozen (sha256 of the p3 prompt and the guard section of `chat.py`: `7a373651c5267f64`). `plan_questions_v5.json` is written **after** this entry: 24 questions, all held out (split "test"), in natural wording and without looking at p3's lists. **Criterion, written before the read:** p3 fully correct on at least 5 more of 24 than p2, and not more `in_scope` errors than p2. p2 and p3 are each read once.

### Held-out read of p3 (2026-10-06, qwen2.5:7b), once each for p2 and p3 on `plan_questions_v5.json`

| 24 held-out questions | p2 | p3 |
|---|---|---|
| Fully correct plans | 17/24 | **20/24** |
| `in_scope` errors | 0 | 0 |
| Right for p3 and wrong for p2 | | 3 ("Super helpful hosts at brunch places", "near the Frankford line", "gastropubs") |
| Right for p2 and wrong for p3 | | 0 |

**Criterion as written before the read:** at least 5 more of 24 than p2 and not more `in_scope` errors. **+3: NOT met.** (The in-scope part held.) Unlike the rewrite criterion of the same day, this one was reachable (p2 scored 17, so +5 was possible), so it is reported as a failure and **p3 is not made the default.**

The four questions both got wrong are four general gaps, not four odd cases: a count written as a digit ("Name 3 good pizzerias": the topic was "3"), "St" for Street in a line's name ("the Broad St line"), the street name before a rail word ("15th Street Station" became a topic), and a superlative outside the lists ("the nicest atmosphere": `nicest`). v5 is now read for both planners and spent.

### p4: the four gaps, by rules, then a fresh set

p4 = p3 plus four general rules, none of them a list of those four questions' words: (1) a digit before a kind or "places"/"spots"/"options" is a count; (2) "St"/"Ave" and the number or name before a rail word belong to the stop and are not a topic ("15th Street Station"), and "Broad St line" and "Market St line" are transit lines; (3) the -est and -er forms of the adjectives p3 knows are read as the superlative (excellent) and comparative (good): nicest, kindest, friendlier; (4) "walkable" is filler. The model prompt is p3's.

p4 is frozen (sha256 of the p3 prompt and the guard section of `chat.py`: `b0e783a669a5fc94`). `plan_questions_v6.json` is written **after** this entry: 24 held-out questions in natural wording. **Criterion, written before the read:** p4 fully correct on at least 4 more of 24 than p2 on the same set, and no `in_scope` errors beyond p2's. p2 and p4 are each read once. If it fails, the default stays p2, p3 and p4 stay available as options, and the record says so.

### Held-out read of p4 (2026-10-06, qwen2.5:7b), once each for p2 and p4 on `plan_questions_v6.json`

| 24 held-out questions | p2 | p4 |
|---|---|---|
| Fully correct plans | 20/24 | **22/24** |
| `in_scope` errors | 1 | 1 (the same question, "Name 4 romantic restaurants", which the model calls out of scope) |
| Right for p4 and wrong for p2 | | 2 ("Is the wait staff polite at Rittenhouse bars?", "walking distance from the El") |
| Right for p2 and wrong for p4 | | 0 |

**Criterion as written before the read:** at least 4 more of 24 than p2 and no `in_scope` errors beyond p2's. **+2: NOT met.** The in-scope part held. **The default stays p2.** p3 and p4 are kept as options (`STREETWALKER_PLANNER=p4`), and v6 is now spent.

What the two held-out sets say together, and what they do not: on v5 and v6, p3 and p4 were right on 5 questions where p2 was wrong and wrong on none where p2 was right (an exact one-sided sign test over those 5 discordant questions gives p = 0.03; two-sided 0.06), but p2 was better than expected on both sets (17/24 and 20/24), so the gain is small, 2 or 3 questions in 24, and below the bars written beforehand. The pooled sign test was not written beforehand and is **not** offered as a reason to adopt. Two questions remained wrong in p4 on v6: "the most attentive baristas" (a service noun, "barista", outside the lists, which is a gap of the same kind) and the model's own scope error on "Name 4 romantic restaurants".

**What this closes and what it does not.** The three misses decision 0029 recorded are fixed under p3 and p4 and covered by tests, and the lists are wider in general English, but every fresh set finds a few more words (v5 found a digit count, "St", a street name before a stop and "nicest"; v6 found "barista"). The lists cannot be finished, and no trend is claimed: the sets differ (p2's misses were 17 of 24 on v4 dev, 3 of 32 on v3, 7 of 24 on v5 and 4 of 24 on v6, because each set was written for a different purpose), so they cannot be compared with one another.


## Rewrite r3: complete questions are not follow-ups (decision 0032), 2026-10-06

**A live check found a defect in both r1 and r2.** Clicking through the chat after an earlier turn about cafes, the suggested question "Where can I sit outside for a drink?" was understood as "Bars in Rittenhouse with good service where I can sit outside for a drink" (r2). A complete question that shares nothing but its subject with the last turn was merged with it. The controls of sets v1 and v2 had not caught this (3 or 4 per half, mostly on a different subject from the earlier turn). Decision 0031's "controls 4/4" was therefore a weak test, and its multi-turn result is **overstated for complete questions**.

**Set `followups_v3.json`:** 48 conversations (24 dev, 24 test), written before r3 existed: per half, **12 complete questions after an earlier turn** (shared area or kind with it, or neither: "Where can I sit outside for a drink?", "Quiet cafes in Roxborough" after a cafe turn, "What do reviewers say about parking?") that must come back unchanged, and **12 genuine follow-ups** of the kinds before (change, add, reference, chain, a place's name). The plan is not scored for the complete questions (the planner has its own sets); they are judged on coming back unchanged.

**Dev, rewrites r1 and r2 as they were (read once each):** complete questions returned unchanged, **r1 8/12, r2 9/12**; all 24 fully correct, r1 14/24, r2 17/24. (On the three-turn histories of the live check r1 was right on the three questions I tried, so the failure depends on the history, which is why the set varies it.)

**r3** is r1's prompt and worked examples, unchanged, plus (1) r2's guard exemption for connectives ("well", "though", "plus"): the real bug behind decision 0031's two add-a-condition misses, and (2) **a completeness guard in code** (`stands_alone`): a message of four or more words that does not open like a continuation ("and", "only", "what about", "same", "not"...), has no reference or continuation word ("those", "them", "it", "one", "too", "instead", "as well", "the second"...) and names no place from the earlier turns is answered as it stands, and the model is not asked. The guard was checked against the three follow-up sets with no model: it blocks one genuine follow-up of 36 ("show me the best", v1 test) and leaves a few non-follow-ups to the model (short thanks, off-topic questions), which handled them before.

| Dev (read once for r3) | r3 |
|---|---|
| v3 dev (24): complete questions unchanged | **12/12** (r1 8/12, r2 9/12) |
| v3 dev: all 24 fully correct | **18/24** (r1 14/24, r2 17/24) |
| v2 dev (16): fully correct, regression only | 14/16 (r1 12/16, r2 15/16) |
| v1 dev (16): fully correct, regression only | 15/16 (r1 14/16, r2 15/16) |

Dev is spent for r3. The six dev misses are not complete-question errors: two references to the whole set where the rewrite lists the places instead of keeping the search ("and are they open on Sundays?" became "Are Rise Bakery and Flour Door open on Sundays?"), one more ("which of those is closest to the subway?"), "is the second one expensive?" (right rewrite, planner topic), "make it cheaper" (not seen as a follow-up), and "any of them take reservations?". **References to the whole set are not fixed (0/3 on dev for r3, 1/3 for r1 and r2).**

### Frozen, and what will judge it

r3 is frozen (sha256 of `chat.py` from the multi-turn heading to the `Answer` class: `81627a267d7fc998`). v3 test is read **once each for r1, r2 and r3**. **Criterion, written before the read:** r3 becomes the default only if (a) at least 11 of the 12 complete questions come back unchanged; (b) its genuine follow-ups (12) are fully correct on at least as many as r1's; (c) its follow-up flag is acceptable on at least as many of the 24 as r1's. Otherwise the default stays r1 (which is the default now: r2 was the default for part of a day and is back out).

### Held-out read (2026-10-06, qwen2.5:7b, planner p2), once for each rewrite, `followups_v3.json` test (24 conversations)

| | r1 | r2 | **r3** |
|---|---|---|---|
| Complete questions returned unchanged (of 12) | 10 | 9 | **12** |
| Genuine follow-ups fully correct (of 12) | 9 | 8 | **10** |
| All 24 fully correct | 19 | 17 | **22** |
| Follow-up flag acceptable (of 24) | 20 | 20 | **23** |
| Plan right without history (the bare message), all 24 | 10 | 9 | 12 |

**Criterion as written before the read** (for r3 to become the default): (a) at least 11 of 12 complete questions unchanged: **12, met**; (b) genuine follow-ups fully correct on at least as many as r1: **10 against 9, met**; (c) flag acceptable on at least as many as r1: **23 against 20, met.** **r3 is the default** (`STREETWALKER_REWRITE=r1` or `r2` switches back).

The complete questions that r1 and r2 rewrote on test were "Gluten free options near the train?" (merged with a bar turn: "Bars in Roxborough with outdoor seating and gluten free options near the train?"), "A place to watch the game with friends" (merged with a brunch turn) and, for r2 only, "Quiet places for a first date". The two genuine follow-ups r3 still gets wrong are "and for dinner?" (the model keeps the earlier topic: "good brunch ... for dinner") and "not too expensive" (three words, with no cue the model reads as a continuation). **References to the whole set** ("either of them", "any of them") **are still the weakest kind**: the model names the places instead of keeping the search; r3 scored 3/3 on test and 0/3 on dev, so that is noise around a known weakness, not progress.

**What this changes in earlier records.** Decision 0031 reported the follow-up flag acceptable on 15 of 16 and the four controls unchanged. Those controls were four per half and mostly changed subject completely, which is the easy case. Measured with twelve per half that share an area or a kind with the last turn, r1, the rewrite 0031 shipped, **rewrote 4 of 12 on dev and 2 of 12 on test (6 of 24, a quarter of the complete questions that shared context with the last turn)**. Its "plan right 14/16 against 7/16" on the 16 invented conversations stands as measured, but it did not include this failure.

**Limits.** 48 conversations by one author, all with one to three earlier turns; the guard is by word lists (it blocks one genuine follow-up of 36 across the three sets); three-word follow-ups ("not too expensive") are not recognised, by the guard's own rule (under four words it asks the model, which says no); and a message that is a complete question and also a follow-up ("Which of the cafes has wifi?" with the cafes shown) is answered as complete.
