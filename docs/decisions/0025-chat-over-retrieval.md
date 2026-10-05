# 0025: Chat over the TableMap retrieval, with a local model

- **Status:** Accepted as a first version. **The planner is measured; the writer's faithfulness is not.** Read "What was measured" and "Limits" before relying on an answer.
- **Date:** 2026-10-05
- **Code:** `chat.py` (plan, search, write, checks, rendering), `chat_eval.py` (planner scoring), `POST /tablemap/chat` in `tablemap_api.py`; question set, labelling rules and run log in `docs/chat-eval/`; 16 tests in `tests/test_chat.py` (one needs the model and an environment variable)
- **Results are private.** The question set and the injection probe are invented and shareable. What the model said about real reviews is in `docs/private/chat-sample.md` (gitignored); this record has no Yelp-derived figure or example.

## The model

`qwen2.5:7b` through the local Ollama server (7.6B parameters, Q4_K_M, 4.7 GB, Apache-2.0, supports tool calls and 32k context; the run uses a 4,096-token window). Downloaded 2026-10-05 with the owner's approval. **Review text goes only to this local server.** `gemma2:9b`, already installed, was tried first as the planner and returned text that was not valid JSON under the few-shot format; it was not investigated further.

## How a question is answered

One question, one answer (no conversation memory). Three steps; the model does the two that need language, code does the rest.

1. **Plan.** The model turns the question into a JSON plan constrained by a schema: whether it is in scope, a short topic, kinds, one area or none, a level (`any`, `good`, `excellent`) for each of the four aspects, near rail, and a sort. Code validates it; anything outside the vocabulary becomes the neutral value, never a guess. An out-of-scope question, or one asking for the worst or lowest of something, gets a fixed reply and no search (the retrieval can only rank from the top; showing the best for "worst service" would mislead).
2. **Search.** Our retrieval (decisions 0023, 0024) runs the plan in hybrid mode: census filters, aspect thresholds, review search, up to two passages for each of five places. `good` and `excellent` are turned into **the median and the upper quartile of the rated places' aspect posteriors**, so they are relative ("better than most of the 102 rated places"), not absolute. A sort by a rating needs at least 10 reviews (a judgement, not tuned). Nothing is loosened when nothing matches: the answer says which conditions found nothing.
3. **Write.** For places with passages only, the model returns for each place whether it answers the question, a one- or two-sentence summary, and up to two quotes. Code then checks every quote: it must belong to a passage of that place, be 3 to 25 words, and sit inside **one fragment** of the passage (a first version let a quote stitch two fragments together, because punctuation was stripped before matching; a test found it). A failing quote is dropped and counted. **Place names, standings and the provisional caveat are rendered by code from the database and constants, never taken from the model.** Standings are words relative to the rated places ("in the top quarter"), with "too few mentions" below five. When the search returns no passages (a question that is only filters) the writer is **not called**: a first run showed it restating standings and contradicting them ("average food" for a place whose food standing was top quarter).

The review text in the writer's prompt is wrapped as data, angle brackets are neutralised so a review cannot close a tag, and the system message says everything inside `<place>` is quoted text to be ignored as instruction.

## What was measured

**Planner, on 48 invented questions** (`docs/chat-eval/`; rules and expected plans written before any model ran, 24 dev and 24 test; each plan scored per field and as fully correct):

| Run | Fully correct | Note |
|---|---|---|
| qwen2.5:7b, dev, first prompt | 17/24 | |
| qwen2.5:7b, dev, after three generic rules added | 21/24 | **tuned on dev: not an estimate** |
| qwen2.5:7b, **test, read once, prompt frozen** | **16/24 (67%)** | scope 23/24, area 20/20, near rail 20/20, kinds 10/10, aspect levels 16 to 20 of 20, topic 8/13, sort 3/3 |

The held-out misses: it sets `food: good` for a dish or cuisine ("Sushi", "Thai food", "good croissants"; a food-quality constraint nobody asked for, which narrows the results), leaves the topic empty for a feature ("open late", "good for groups", "watching sports"), and called "Dog friendly places" out of scope. Each plan is echoed to the user as "Searched for: ...", so a wrong plan is visible. The test split has now been read; a planner change must be judged on a fresh invented set. Median time per plan was about 4 s with the model loaded.

**Prompt injection, on the invented world** (a review that tries to give the model orders, three variants): none was followed literally (no "HACKED", no claim that another place is the best). One variant, with a fake `SYSTEM:` line, still disturbed the answer: the model presented a place that does not have a patio with the claim that it does, and marked the genuine patio place as not relevant, while the quote it attached was real but irrelevant. The quote check cannot catch that, so a **summary can be steered or wrong even when every quote is verbatim.** Three variants, one run each; this shows a failure mode exists, not how often it happens.

**On the real reviews** (eight invented questions, private notes): answers were produced and rendered, the model's quotes were checked, and a substantial share of them were not verbatim and were dropped, so the check is doing real work. Standings-only answers and out-of-scope questions behaved as designed.

## Limits

- **Writer faithfulness is unmeasured.** Summaries are model paraphrase of the passages and are shown as "model-written, not checked". Measuring them needs a fresh invented set where the facts are known, with answers judged by rule (does the summary assert something the passages do not?).
- **"Relevant" is the model's judgement,** and it is noisy: a place whose passage says "terrace" was judged not to answer a question about a patio. The places judged irrelevant are listed apart, by name, not hidden.
- **Planner: 67% fully correct on held-out questions.** Mostly harmless extra or missing constraints, but they change which places come back.
- **No ascending ranks, no multi-turn, no comparisons** across areas beyond what one search returns.
- **Speed and memory.** A whole answer took 30 to 150 s in the sessions measured, far more than the planner alone. Much of it was memory pressure on this 16 GB machine: three models resident in Ollama (about 12 GB) pushed 10 GB into swap, and once the runner wedged and returned empty replies (the client now reports this and names the remedy, `ollama stop <model>`). Keep one chat model and the embedding model loaded; the first request after a load adds about 30 s.
- **Names are the census names,** which for licence-only places are legal names ("pho mi rittenhouse inc").
- **Everything in 0023 and 0024 still applies:** provisional aspect numbers, reviews to January 2022, local and unauthenticated, nothing shown publicly without the checks in 0001.

## Not done

1. A writer-faithfulness evaluation, and a planner v2 judged on a fresh invented set (the two big food-aspect and topic misses above).
2. A second pass that checks a summary against its quotes, or dropping summaries in favour of quotes only.
3. Ascending sorts, conversation memory, a UI, and evaluation in CI (the pure parts of `tests/test_chat.py` and the retrieval tests would run against a scripted model with only Postgres).
