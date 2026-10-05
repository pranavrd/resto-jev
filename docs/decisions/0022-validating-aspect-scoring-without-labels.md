# 0022: Validating aspect scoring without human labels

- **Status:** Accepted
- **Date:** 2026-10-04
- **Code:** `aspect_probe.py` (constructed test set and hard cases, 11 tests), `tests/test_aspect_probe.py`; raw results in `docs/probe/` (invented text, so they can be shared)
- **Reproduce:** `.venv/bin/python -m streetwalker.aspect_probe [--save FILE]`, `... --hard FILE`, or `--from FILE` to re-evaluate saved answers without calling Jev

## The decision this follows

The owner labelled 10 of the planned 180 reviews and has decided **not to label by hand any further**. That removes the yardstick decisions 0018 and 0021 relied on: the aspect scores will not be checked against people, and neither will the building review queue (so the cascade's human tier stays an oracle, decision 0018).

What that does and does not change:

- **Unchanged:** every rule in 0021. The rating stays **provisional**, nothing is claimed as validated against human judgement, and the composite weights stay frozen and were never tuned on any label.
- **Changed:** "until the first batch has spoken" can no longer be met, so the claims this project can make are fixed by what evidence *exists*, listed below with its limits. The 10 labels are kept in the database and are too few to conclude anything.
- **Not done:** an AI annotator standing in for the person. It would measure agreement between two models, not accuracy, and would blur what a "label" means in this project. It remains an option, to be stored separately and called what it is.

## What replaces the labels

**1. A constructed test set (176 invented reviews, the truth known by construction).** Three-phrasing banks of single-aspect sentences at each of five levels, combined in three ways. The test checks, before any API call, that each sentence is about its own aspect only and that the tone sentences ("Five stars from me!", "One star from me.") say nothing about any aspect. The design was fixed before Jev saw it.

| Question | Result on the invented set |
|---|---|
| Does Jev notice an aspect that is there? | recall 100% for food, atmosphere and service; **92% for value** |
| Does it invent one that isn't? | 0% false mentions on 512 chances (432 aspects a sentence is not about, and 80 on 20 tone-only reviews) |
| Does the score match the known level (0 to 4)? | within one level 100% of the time; exact 88 to 94%; mean error 0.12 to 0.20; slightly low in the middle of the scale (levels 1 and 3 land up to 0.3 low) |
| Does one aspect's sentiment leak into another's score? (36 two-aspect reviews, 72 scores, one aspect good and one bad) | **no**: the weight on the other aspect's level is 0.00 |
| **Is there a halo?** The same aspect sentence with a positive and a negative overall-tone sentence | **yes, a small one: the score is 0.23 of a level higher (95% interval +0.17 to +0.30) beside "five stars, recommended" than beside "one star, never again"**; about 0.3 for atmosphere and service, about 0.17 for food and value; 17% of pairs differ by more than half a level |

**2. Twenty hand-picked hard cases** (sarcasm, negation, a hedge, backhanded praise, expensive-but-worth-it, delivery, a Spanish sentence, words like "bad reviews" that are not about the place, three aspects at once). 77 of 80 aspect judgements are right. This says where it fails, not how often. **All three misses are an aspect mentioned implicitly:** "the room was freezing" is not taken as atmosphere; "it cost us a fortune" is not taken as value (its score, 1.4, is right, but mention falls below the threshold); a bare "$14 for a cocktail" is not taken as value (arguably correct).

**3. The unlabelled checks of decision 0020** (scores rise with the stars, aspects add information beyond them, confidence is informative except for value) and **10 human labels** (a descriptive look only; see the private notes).

## What can and cannot be said now

**Can say, with these limits:** Jev's aspect scoring handles clear cases, sarcasm, negation, mixed and multi-aspect sentences, and one other language on invented text; it does not mix up aspects; its scores carry a small halo from the reviewer's overall verdict (about a quarter of a level between the best and the worst overall verdicts); and it under-detects implicit mentions of value and atmosphere.

**Cannot say:** that the scores match a person on real, messy reviews; that the rating or any ranking is accurate; that the halo is the same size on real reviews as in a constructed pair (real reviews hold both the aspect and the verdict in more entangled ways); how often implicit mentions are missed in the real reviews.

## What this means for the provisional rating

- **A small halo pushes the aspects together.** Some of the closeness between aspects across places (food and service especially) is probably this, not the restaurants. It is too small to explain all of it, but it is a known upward bias on the aspect correlations and on any "aspect adds nothing beyond the stars" reading.
- **Value and atmosphere rest on explicit mentions.** Where a reviewer states a price complaint or a bargain, it counts; a passing "cost a fortune" may not. A place's value score is an estimate from the reviewers who chose to talk about price, a selected group, and probably undercounts. The rating's intervals do not include this bias.
- **The rating stays `provisional`.** Lifting it takes a migration that states the basis. The owner may decide that this evidence is enough for some use; my recommendation is to keep it provisional and to describe any use as "scores from an LLM, tested on constructed cases, not validated against people".
- A fix for the halo (telling Jev to ignore the overall verdict) is **not** tried here: it would be tuned and judged on the same probes. If wanted, write a second probe set first and judge the change on that.

## Other validation that needs no labels, not done

- Prompt stability: reword the questions (a version a2) and compare scores on the same reviews. Cheap; it shows sensitivity to wording, not accuracy.
- A lexicon baseline (keyword sentences scored with a sentiment lexicon): an independent, non-LLM floor to compare agreement with.
- A second AI annotator on batch 1, stored apart from the human labels.
