# 0028: Recall and cost of the relevance check; an extractive answer mode

- **Status:** Accepted. The check of decision 0027 is **unchanged**; a candidate failed its pre-registered criterion. An opt-in extractive mode (w4) is added. w3 stays the default.
- **Date:** 2026-10-05
- **Code:** `chat_verifier_eval.py` (the set, the methods, the runner), `chat.py` (`verified_excerpts`, `extract_quote`, writer `w4`), `tablemap_api.py` (`style`), tests in `tests/test_chat_verifier_eval.py` and `tests/test_chat.py`; set, rules, runs and log in `docs/chat-eval/verifier/`
- Everything measured on the set is invented and shareable. The timings on real reviews are in `docs/private/` and summarised here without Yelp text.

## What was asked

Improve the check's recall and the cost of an answer (decision 0027 measured recall around 73% and answers of up to six minutes).

## The instrument

A fresh set for the check alone: 12 invented topics (reservations, happy hour, trivia night, coffee, wheelchair access, sushi, pizza by the slice, ...), split by topic (6 dev, 6 test), 16 passages per topic in 9 categories (direct, paraphrase, buried among neutral sentences, planted-instruction variants, and four kinds of "no": incidental mention, negated, unrelated, buried). Eight places of two passages per topic, so passage-by-passage and one-call-per-place methods are compared on the same places. A test checks that no sentence of the faithfulness set and no prompt example is reused. The test injection phrasings were written after the method was frozen, in styles the sanitizer was not designed for.

## What was found

1. **The weakness on this set is precision, not recall.** The current check had recall 88% (dev) and 90% (test) and said "yes" to 11 of 48 "no" passages on the dev topics, half of the incidental mentions, and to 2 of 48 on the test topics. So its recall depends on the topic (70% to 73% on the faithfulness set, about 89% here) and its guard against incidental mentions holds for some phrasings and not others. In the real sample it let through a review of someone who is "not even close to being a vegetarian" for a vegetarian question.
2. **Seven variants were tried on dev:** a stance output (has it / lacks it / only elsewhere or in passing / silent), per passage and grouped, a sentence-level filter for planted instructions, a topic hint, a "rescue" of silent verdicts whose topic words are in the passage, and a lighter prompt. The best on dev (`grouped_light`: hint, four of eight worked examples, one call per place) went from 11 false positives to 0 at 88% to 90% recall.
3. **It did not hold on the test topics.** 2 false positives against 2 for the baseline and recall 81% against 90%. Both pre-registered criteria failed, so it is not adopted. Its dev gain was specific to the dev topics and partly built to them. The rescue made things worse (5 false positives on dev). The sentence filter changed almost nothing.
4. **The check is not the cost.** On real questions: plan 4 to 10 s, check about 1 s per call (5 to 12 s per answer), search under 1.5 s, **writer 38 to 53 s**, from generating 400 to 700 tokens of summaries and quotes at about 15 tokens per second. A grouped check was no faster in wall time than per-passage ones. The six-minute answers of decision 0027 were this plus memory pressure (6 to 10 GB of swap); with 6 GB in use now, answers took 31 to 44 s.

## What was built: extractive mode (w4)

The same plan and check, then no model-written text: for each place that passes, the first passage that passed is cut to 25 words, checked by the same verbatim test, and shown with the standings. Requested with `"style": "quotes"` on `POST /tablemap/chat`; the default `"summary"` is writer w3.

| (three real questions) | w3 | w4 |
|---|---|---|
| Time | 31, 40, 44 s | 10, 12, 17 s |
| Places shown with a quote | 0 to 2 of 3 to 5 | all |
| Places shown with a model-written sentence | 1 or 2 | none, by design |

There is nothing to be unfaithful in the text. The risk moves entirely to the check, whose mistakes the quote now shows the reader. Its quotes are the first fragment of the passage, which is centred on the query terms by the search but is not always the answering sentence, and a cut at 25 words can end mid-sentence.

## Limits

- **The set is templated and small** (48 places, 96 passages per split; 12 topics) and read by an AI, not a person. A label can be argued. Real reviews are longer and messier.
- **This set's test half is now read for two methods;** a further change to the check needs another fresh set. The recall difference between this set and the faithfulness set shows how much the figure depends on the items.
- **The incidental-mention weakness is not fixed.** The check can still show a place because its reviewer mentioned the topic about someone else. It may be worth a stricter second look at borderline places, a larger model, or showing the quote next to every place (which w4 does).
- **No number here is validated against people.**

## Not done

1. A fix for incidental mentions that holds on new topics (needs a fresh set, and probably a stronger reader than a 7B model).
2. Cutting the writer's time in w3 without changing what it says (shorter outputs change its behaviour and need a fresh faithfulness set).
3. A better quote choice for w4 (the answering sentence, not the first fragment).
4. A planner v2, ascending sorts, multi-turn, a UI, and CI.
