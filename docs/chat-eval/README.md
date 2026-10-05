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
