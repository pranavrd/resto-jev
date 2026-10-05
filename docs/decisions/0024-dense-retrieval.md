# 0024: Dense review retrieval, fused with the lexical ranker

- **Status:** Accepted for the retrieval layer. Quality on real reviews is **not measured against people**; see "What was checked".
- **Date:** 2026-10-04
- **Code:** `embeddings.py` (Ollama client, query cleaning), `embed_reviews.py` (resumable job), `tablemap.py` (`retrieval_ctes`, fusion), `tablemap_api.py` (`mode`, `min_similarity`, `dense_k`); migration 023 (`review_embedding`); tests in `tests/test_tablemap.py` (24, one of which needs the model and skips without it)
- **Private notes:** figures from the real reviews are in `docs/private/dense-retrieval-notes.md` (gitignored). This record has method, the invented-data evaluation (shareable) and caveats.
- **Reproduce:** `ollama pull nomic-embed-text`, then `.venv/bin/python -m streetwalker.embed_reviews` (about 17 minutes for all reviews, resumable).

## The model

`nomic-embed-text` through the local Ollama server: 137M parameters, Apache-2.0, 768 dimensions, 274 MB, the build's context length is 2,048 tokens (review text is cut at 6,000 characters before sending). It was downloaded on 2026-10-04 with the owner's approval. Documents and questions get the model's own task prefixes (`search_document:` / `search_query:`). Every vector is stored with the model name and digest (`nomic-embed-text@0a109f422b47`), because vectors from different models are not comparable. **Review text goes only to the local server, never to a third party.** The vectors are derived Yelp data and are private like the rest: they live in the local database and go with it at the end of the Data's term (2027-10-03).

## How retrieval works now

`text` has three modes: `lexical` (Postgres full-text), `dense` (exact cosine distance between the question's embedding and each review's) and `hybrid` (the default in the API, both fused).

- **Scope first.** Retrieval runs over the reviews of the places that pass every other filter (kind, area, transit, aspect thresholds), then the places are joined back, so "bar + patio" cannot lose its answer to a better-matching restaurant. The scan is exact (no vector index): the table has one row per review, and an index that filters after the nearest-neighbour step is the wrong tool here.
- **Fusion.** Each ranker contributes a ranked list of reviews (lexical: every match; dense: the closest `dense_k`, default 100). A review scores the sum of 1 / (60 + rank) over the lists that hold it (reciprocal-rank fusion), and a place's text score is the sum over its reviews. Passages for a place use the same fusion over that place's reviews.
- **Exclusions hold for dense candidates too.** Words after a minus sign are removed from the question before it is embedded, and any review containing one is dropped from the dense list.
- **No embedding server, no silent fallback.** Dense and hybrid return a 503 that names `mode=lexical` as the way out; the lexical mode needs nothing running.
- Each response says which retrieval ran (mode, embedding model, how many reviews have vectors), and each passage carries its cosine similarity (null for a lexical-only match).

## What was checked

**On invented data** (5 places, 11 reviews, 13 queries with the relevant places fixed by hand), real model, place-level ranking, recall of the relevant places in the top three and mean reciprocal rank (MRR):

| Mode | recall@3 | MRR | Places returned |
|---|---|---|---|
| lexical | 0.38 | 0.38 | 0.4 on average (it returns nothing for most paraphrases) |
| dense | 0.85 | 0.64 | all 5 (dense returns the nearest reviews, however far) |
| hybrid | 0.85 | 0.81 | all 5 |

The synonym queries lexical missed in decision 0023 ("al fresco", "outdoor seating") now put the right two places on top. **Caveats on this table:** the set is tiny; several queries were looked at while the mode was being built, so it is a regression guard with a measured floor (the test asserts the floors, not these exact figures) and not an unbiased estimate; and it is a ranking over five places, where chance is not far from the result. Two query families still fail: "inexpensive" and "cheap eats" (the cheap place is not in the top three, because another review scores higher on the review level) and a query for a dish ("lamb dinner") where a place with three reviews outranks the right place with two, which is the review-count bias described below.

**On the real reviews** (numbers in the private notes): a keyword lexicon per concept is an independent signal that does not use the model, though it undercounts paraphrases and is not a human label. For five concept queries the dense top 20 contains a keyword hit in 75% to 100% of reviews against base rates of 1% to 11% over all reviews; a nonsense query ("quantum physics lecture") returns almost none (1% of its top 100) and its closest review has a clearly lower similarity than the closest review of the real concepts. So the model is finding what the words describe. That is **a plausibility check, not accuracy**: nobody has judged the real results, and the lexicon has its own blind spots.

## Caveats

- **No cosine floor.** On the invented reviews the similarities of relevant and irrelevant reviews overlap (a relevant paraphrase at 0.52 against an irrelevant review at 0.51; nonsense queries reach about the same maximum), and on the real reviews a rare but real topic has a lower similarity at rank 20 than a common topic has at rank 100. No single threshold separates "relevant" from "not", so `min_similarity` exists as a parameter and has **no default**. Dense matching is nearest neighbours, not a relevance verdict: a query nothing matches still returns places. Whatever reads the passages (the chat layer) has to judge relevance itself.
- **The text score favours places with many reviews** (a sum over reviews). The invented set shows it; the alternatives (best review only, or the share of a place's reviews) were not tried, because choosing one on the same five places would be tuning on the judging set. A fresh evaluation set is needed first.
- **Dense search depends on the language and wording of the model's training;** reviews in other languages were embedded like any other and not checked.
- **The 2,048-token context** truncates the longest reviews, which also means the end of a very long review is not searchable densely (it still is lexically).
- **Everything in decision 0023 still applies:** the aspect numbers are provisional, the reviews end in January 2022, and the router is local and opt-in.

## Not done

1. A **fresh, larger evaluation set** (invented, with relevance fixed before the queries are run) to choose between sum, max and share for the place score, and to test the lexical, dense and hybrid modes without having looked at the queries.
2. The **chat layer** (see decision 0025 when it exists).
3. A **second embedding model** for comparison, and chunking of long reviews.
