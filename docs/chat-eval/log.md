# Chat planner evaluation log (invented questions, no Yelp data)

Set written before any model ran on it (`plan_questions.json`, rules in README.md). Plans are scored per field and as "fully correct" (every scored field right).

| Date | Model | Split | Prompt | Fully correct | Notes |
|---|---|---|---|---|---|
| 2026-10-05 | qwen2.5:7b | dev | first draft | 17/24 | in_scope 24/24; misses: topic left empty for a dish or occasion, one area forced onto a two-area comparison, "drinks" not treated as food |
| 2026-10-05 | qwen2.5:7b | dev | revised once on dev (three generic rules added) | 21/24 | **tuned on dev, so not an estimate** |
| 2026-10-05 | qwen2.5:7b | **test** | revised, frozen | **16/24** | read once. in_scope 23/24, area 20/20, near_rail 20/20, kinds 10/10, aspects 16-20/20 (food worst: sets "good" for a dish, "Sushi", "Thai food"), topic 8/13 (empty for "open late", "groups", "watching sports"), sort 3/3. One false out-of-scope ("Dog friendly places") |
| 2026-10-05 | gemma2:9b | dev | revised | not scored | the first request returned text that was not valid JSON under the few-shot chat format, so the run stopped; not investigated, since the owner chose qwen2.5:7b |

The test split has now been read for this prompt. A change to the planner prompt needs a fresh invented set to be judged on; do not tune on this one again.
