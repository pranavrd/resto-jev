# 0023: TableMap retrieval: places, provisional aspect ratings and review text in one query

- **Status:** Accepted for the retrieval layer. The chat layer and dense embeddings are **not built** (see "Not done").
- **Date:** 2026-10-04
- **Code:** `tablemap.py` (query builder, excerpts, result shaping), `tablemap_api.py` (the router), `api_common.py` (place filters and shaping shared with `api.py`), `search.py` (`parts()` split out of `build()`), migration 022 (full-text index); 15 tests in `tests/test_tablemap.py`
- **Results are private.** The tests use invented places and reviews only. No figure or example derived from the Yelp Data is in this record.

## What was built

One search that combines three kinds of constraint over the census `place` table:

| Kind | How | Source |
|---|---|---|
| Structured | every filter of `/places` (kind, area, neighborhood, point and radius, SEPTA stops, rail, routes, trips) | `place`, through the same `search.parts()` the public API uses |
| Aspect | a minimum for food, atmosphere, service or value, on the posterior mean or on its 95% lower bound (`min_by=lower`: "confidently at least this good"), and a minimum number of reviews | `restaurant_aspect`, `restaurant_rating` of the latest rating run |
| Review text | web-search syntax (`words`, `"a phrase"`, `-excluded`, `a OR b`); a place matches when at least one of its reviews does | Postgres full-text search over `yelp_review`, reached through `place_review` |

A place with no linked reviews is listed by a plain search (with `reviews: null`) and never by a text search. Results can include up to five matching passages per place with the aspect scores Jev gave that review: a level is shown only where the aspect was judged mentioned, because the score of an unmentioned aspect is meaningless.

Endpoints, under `/tablemap`: `GET /search` (all of the above plus `rank_by`, `excerpts`, paging) and `GET /places/{id}` (one place with its aspect posteriors and, given `text`, its matching passages).

## The rules this follows

1. **Opt-in and local.** The router is mounted only when `STREETWALKER_TABLEMAP=1`. The default app keeps its Yelp-free surface, and a test starts the app in a fresh process with and without the flag and checks the paths: nothing named `tablemap`, `yelp` or `review` without it, both TableMap paths with it. It is read-only and has no login; do not expose the port.
2. **Provisional everywhere.** Every response carries `status: "provisional"`, the banner of `rating.py`, the rating run, aspect run and weights version it read, and the date the reviews end. Every rated place repeats `status: "provisional"`. A sort by a rating is opt-in (`rank_by`) and replaces the place sort; the default order is alphabetical, not a ranking. The composite is returned with its credible interval and its rank interval, so a rank is never shown alone.
3. **Downstream code reads the usable links.** Reviews come only through the view `place_review`, which is built on `yelp_link_usable` and the aliases. A test fails if either module mentions `yelp_link` (the unfiltered table) or a label table.
4. **Yelp content leaves only through this router,** and each response names its source (the Yelp Open Dataset, snapshot to January 2022) and that it is private (decision 0001). Display or redistribution is a separate decision and needs the checks in 0001 first.
5. **Every user value is a bound parameter.** The SQL text holds only fixed names (the four aspects, fixed sort expressions). Tests pass an injection string through the text and name filters.

## Checks

- **Retrieval evaluation on invented data** (`LEXICAL` in the tests): nine queries over five invented places and eleven invented reviews, with the relevant places fixed by hand when the reviews were written. Exact match on all nine, including a stem ("waiting" finds "Waited"), a phrase, an exclusion, an OR and a combination with a kind filter. This shows the plumbing and the query syntax work; it does **not** show retrieval quality on real reviews, which have not been judged.
- **Known misses are recorded as tests** (`LEXICAL_MISSES`): synonyms the reviews express in other words ("al fresco" for a patio or terrace, "inexpensive" for cheap) return nothing. The test asserts that they still return nothing, so the day dense retrieval makes them work the test fails and the eval and this record get updated rather than the gap being forgotten.
- The tests build their world inside one transaction and roll it back; the real tables are untouched (checked after the run). I also ran the endpoints against the real database for status codes and result shapes (a plain search, text with passages, aspect thresholds with a lower bound, a text query at a point sorted by distance, injection, an all-stopword query, bad parameters). That checked that they run, not that the results are good.

## Caveats

- **Lexical only.** No synonyms, no paraphrase, no "cheap sushi" meaning "good value": that is what dense embeddings are for, and they are not built. "Hybrid" here means structured filters plus aspect constraints plus lexical review retrieval in one query.
- **The text score favours places with many reviews.** It is the sum of the full-text rank over a place's matching reviews, so a place with hundreds of reviews outranks a small one that matches every review. `n_reviews` in `text_match` and `reviews.n_reviews` are returned so the share can be read; no normalised score was chosen, because choosing one without judged results would be a guess.
- **A query made only of stopwords matches nothing,** not everything. A query in another language matches only English stems.
- **`reviews_through` is January 2022.** The census describes 2026; a place can have changed hands or closed since its reviews were written (decision 0019).
- **The aspect numbers are the provisional ones** (decision 0021): LLM scores tested on constructed cases (decision 0022), a small halo, implicit value and atmosphere mentions under-detected, never validated against people. An aspect threshold or a `rank_by` therefore filters or sorts on those numbers with those limits, and the aspect posteriors do not include the value and atmosphere under-detection bias.
- **Excerpt headlines mark the match with « and »,** not HTML. Review text itself is unsanitised; anything that renders it must escape it.
- **Full-text indexing duplicates review text inside Postgres** (the GIN index). It is in the same local database as the reviews and goes with them at the end of the Data's term (2027-10-03).

## Not done

1. **Dense retrieval.** Needs an embedding model (a download that needs the owner's approval) and a `review_embedding` table; the vector ranker would be fused with the full-text rank in `load_excerpts` and in the place-level text score (reciprocal-rank fusion is the plan). The synonym misses above are its first test.
2. **The chat layer.** Retrieval is the tool it would call: the language model turns a question into `search` parameters, reads the passages and scores, and answers with the provisional caveat. Open choices before building it: which language model (Jev is a decision model, not a chat model; the repository holds no key for a hosted chat model, and the only local model is a 3B vision-language model that was a poor reader in decision 0018), and what the answers must always say. Review text sent to a hosted model rests on the owner's reading of the agreement (decision 0001).
3. **Evaluation in CI.** There is no CI in the repository. The retrieval evaluation above is self-contained (invented data, one rolled-back transaction) and needs only a Postgres with PostGIS, pg_trgm and pgvector, so a workflow could run it; adding one is a separate step.
4. **No UI.** The map UI stays Yelp-free.
