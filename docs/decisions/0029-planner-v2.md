# 0029: Planner p2: the model decides scope and topic, the question decides the rest

- **Status:** Accepted. p2 is the chat's default planner; p1 is kept unchanged for reproduction.
- **Date:** 2026-10-05
- **Code:** `chat.py` (`PLAN_SYSTEM_P2`, `PLAN_SHOTS_P2`, `guard_plan`, `detect_levels`, `code_kinds`, `code_area`, `code_sort`, `residual_topic`, `PLAN_VERSION = "p2"`), `chat_eval.py` (`--set`, `--planner`, scorer v2), `docs/chat-eval/` (sets v2 and v3, rules, log, raw runs); 8 more tests
- Everything measured is invented and shareable.

## What was wrong with p1

Decision 0025 measured 16 of 24 fully correct plans on held-out questions. The misses were of three kinds: it set a food-quality level for a dish or cuisine ("Sushi", "Thai food"), it left the topic empty for a feature ("open late", "groups"), and it called a question about dogs out of scope. On a fresh set (v2 dev) p1 got 18 of 32, with the same kinds of miss plus a forced single area for a two-area comparison and a sort the question did not ask for.

## What p2 is

1. **A broader prompt and new worked examples.** Scope is defined by what the places are like or offer (pets, children, parking, access, hours, payment, music, outdoor tables, delivery) and excludes other cities, directions, reviewer identities and requests about the prompt; a dish, cuisine or drink is never an aspect; the examples were rewritten (p1's own "good oysters" example had taught the wrong thing).
2. **Code reads the structured fields off the question** after the model answers (`guard_plan`):
   - **kinds** from kind words (pub and brewery are bars, coffee shop is a cafe, ...), so a kind is never invented and never dropped;
   - **area** from the area words, `any` when two are named (so "Passyunk" works);
   - **near rail** from rail words (subway, train, trolley, SEPTA, station, ...);
   - **aspect levels** from a quality word right before an aspect word (one intensifier may sit between) or after "is/are": "great service", "the food is really good", "best value", price words imply good value, complaints (overpriced, pricey) do not count, and "good tacos" or "Thai food" give nothing. The model's own level survives only when the question has an aspect word and a quality word somewhere (it may have read a paraphrase);
   - **sort** from best, top, highest, overall, most: the single named aspect if there is one, else overall, otherwise relevance.
3. **The topic stays the model's,** but a topic none of whose words is in the question is dropped, and an empty topic is filled with what is left of the question after kinds, areas, rail words, filler, quality words and the aspects already used are removed ("open late", "dog", "staff").
4. The model still decides **scope**, and the rest of the plan fills in only for in-scope questions.

This is a deliberate shift: structured fields the model got wrong, in ways a rule over the question gets right, are now decided by rules. It is auditable (a test per rule) and it fails in a different way: **a rule only knows its word lists.**

## How it was judged

| Set | p1 | p2 |
|---|---|---|
| v2 dev (32), used to build p2 | 18/32 | 32/32 (not an estimate: the rules were written from its misses) |
| **v3 (32), written after p2 was frozen, decides** | **19/32** | **29/32** (95% interval 76% to 97%, against 42% to 74%) |
| v2 test (32), not blind for the vocabulary | 20/32 | 32/32 |
| v1 test (24) and v1 dev (24), misses known beforehand | 16/24 and 21/24 | 23/24 and 24/24 |

On v3, p2 was right where p1 was wrong on 13 questions and wrong where p1 was right on 3 (exact sign test p = 0.02), and it made no scope error against two for p1. The criterion was written in the log before the read: at least 5 of 32 better, scope errors not more. Both met. The scorer was changed once during the work (copying the question as the topic is wrong only for a question of more than six words; the first rule penalised "Sushi" and "dog friendly patios"); it changes no earlier count.

## Limits

- **Three misses on v3, left unfixed:** a quality word outside the lists ("terrific staff": the service level is lost), a rail line named without a rail word ("Broad Street Line": near-rail false, and the topic becomes the line's name), and a number word as a topic ("the three best bars"). Real users will find more; the lists are short and English.
- **The vocabulary was written knowing the v2 questions,** which is why v3 was written afterwards; but v3 is still written by the same author, 32 questions, and one reading of what is "correct". Interval 76% to 97%.
- **Slower:** the longer prompt makes a plan take about 7 s against about 4 s.
- **A wrong plan is still the weakest point.** The answer begins with "Searched for: ..." so it is visible.
- **The first-set numbers for p2 (23/24 and 24/24) are not evidence:** p2 was designed knowing p1's misses there.

## Not done

Recall of the model's scope judgement on adversarial wording (a poem about brunch, a prompt-injection that mentions restaurants); lists in languages other than English; ascending sorts; multi-turn; a UI; CI.
