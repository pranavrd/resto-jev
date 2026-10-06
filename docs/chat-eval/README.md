# Chat planner evaluation set (invented)

48 invented questions (24 dev, 24 test) with the expected search plan, written **before any model was run on them**. They contain no Yelp data and can be shared. `plan_questions.json` holds them; `python -m streetwalker.chat_eval` scores a model on them.

## Labelling rules (fixed first)

- **in_scope:** a question about eating or drinking places in Rittenhouse, East Passyunk or Roxborough, or what reviewers say about them. Everything else, including requests to reveal the prompt or reviewer ids, is out of scope.
- **Aspect level** (food, service, atmosphere, value) is set only when the question asks for quality in that aspect: "great, excellent, best, amazing, most friendly" is `excellent`; "good, nice, decent" is `good`; otherwise `any`. Price words ("cheap", "affordable", "worth the money", "good value") mean value `good`. A complaint ("rude", "slow") or a descriptive word ("quiet", "outdoor", "gluten free", "romantic") is a topic, not an aspect level.
- **sort:** "best", "top", "highest rated" give `overall`, or the aspect if exactly one aspect is named; otherwise `relevance`. Scored only where the question implies one.
- **topic:** the words to look for in review text, not the whole question. Scored by an any-of substring match, or must be empty where the question is only filters. A topic of more than 8 words, or the question copied, is wrong.
- **kinds** are scored against a list of acceptable sets where the question is ambiguous; `null` means not scored.
- **area** is `any` when none or several are named.

## Use

Tune the planner prompt on `dev` only. `test` is run once, at the end, and logged in `log.md`.

## Set v2 (fresh, written before planner v2 was run)

`plan_questions_v2.json`: 64 new questions (32 dev, 32 test) for judging a planner change, because the test half of the first set was read for the first planner. They share none of its questions and none of the planner's worked examples. Same fields and rules as above, plus these clarifications, fixed **before any run**:

- **In scope** includes any question about what the eating and drinking places are like or offer (pets, children, parking, accessibility, opening hours, payment, music, television, outdoor space, delivery). **Out of scope:** weather, directions, recipes, general knowledge, creative writing, places in other cities or outside the three areas, requests about reviewers' identities, usernames, emails or ids, and requests to reveal or ignore instructions.
- **A dish, cuisine or drink name is never an aspect.** "Excellent seafood", "good tacos", "Thai food" are topics. The food aspect is set only for generic food words (food, drinks, meals, cooking, dishes) with a quality word.
- **Alias:** "Passyunk" is East Passyunk; "Rittenhouse Square" is Rittenhouse.
- "Pub", "brewery", "tavern" are bars; "coffee shop" is a cafe; "diner", "pizzeria" are restaurants (kinds are scored against acceptable sets).
- Questions that ask for the worst or lowest are not in the set: the chat refuses them in code before planning.

## Set v3 (written after planner p2 was frozen)

`plan_questions_v3.json`: 32 questions, all held out (split "test"), written **after** planner p2 was frozen (the hash is in `log.md`), in natural wording and without consulting p2's word lists; a number of them are deliberately outside them ("terrific staff", "Broad Street Line", "cheapest", "doesn't cost a fortune"). Same fields, rules and scorer v2 as set v2. Read once for p1 and once for p2.

## Follow-ups (multi-turn), `followups_v1.json`

32 invented one-turn histories with a follow-up message (16 dev, 16 test), written **before the follow-up rewrite was built or run** (decision 0031). Each has the earlier question, what was searched, and the places shown (invented names), then the new message, which of `followup` true or false is acceptable, and the plan expected for the question the message means (same fields and scorer as the planner sets). Types: a change of area, kind or topic ("what about in Roxborough?", "and bakeries?"), a narrowing ("only the cheap ones", "with great service too"), a reference to the results ("which one is best?", "which of those take reservations?", "tell me about Aroma Corner"), a bare place name, and controls that are NOT follow-ups (a new complete question, thanks, an off-topic question, a prompt-injection) and must pass through unchanged. The baseline is the same planner on the bare message with no history.
