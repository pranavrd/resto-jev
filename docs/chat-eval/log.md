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
