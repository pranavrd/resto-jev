# 0020: Yelp reviews for the linked places, and aspect scoring with Jev

- **Status:** Accepted for the scoring run; **the scores are not validated** (no human labels yet), see "What this does not show"
- **Date:** 2026-10-04
- **Code:** `ingest/yelp_reviews.py`, `aspects.py` (questions, 5 tests), `aspect_run.py`, `aspect_report.py`; migrations 018 (`yelp_review`, view `place_review`) and 019 (`aspect_run`, `aspect_request`, `aspect_score`); `jev_client.py` now parses Score answers
- **Results are private.** Counts, costs, rates and examples derived from the Yelp Data are in `docs/private/aspect-results.md` (gitignored; agreement 4E and 5, decision 0001). This record covers method and caveats only.
- **Hosted processing.** Review text is sent to the hosted Jev API. That is the owner's decision (decision 0001: both versions of the agreement are quoted there, and they word the third-party rule differently).

## Reviews

The reviews of the usable links (decision 0019) are loaded into the local database. The 5 GB review file is streamed out of the zip and the tar into a filter, so it is never written to disk; only reviews of linked businesses (and duplicate listings of them) are kept. `user_id` is dropped on the way in: nothing here needs to identify a reviewer. `place_review` joins reviews to places through the usable links and aliases; use it, not the raw table.

A review of a **hotel** turned up under a restaurant while reading samples, which showed that a correct match to the wrong *kind* of listing is still a wrong source of reviews. The matcher now requires a dining category and rules out lodging listings (a restaurant inside a hotel reviews the hotel's listing, not the restaurant). Such links are capped at low, and relinking deletes the reviews, and through them the scores, of any business that is no longer usable.

## Aspect scoring

Four aspects, as planned in the roadmap: food, atmosphere, service, value. Each is two questions in one request, one request per review (so eight questions): a **mentioned?** yes/no, and a five-level **sentiment Score**. The wording follows the Jev documentation:

- **One dimension per question**, each aspect defined in a sentence (what counts as food, atmosphere, service, value).
- **Levels are described as situations**, not numbers, because Jev judges every level on its own against the text and never sees the numbers. They run from clearly negative (0) to clearly positive (4), with a middle level for mixed or flat.
- **The two questions are separate** because a Score answers "how does the reviewer feel?" even when the review is silent. The mentioned probability is the gate; the question text tells Jev to pick the middle level when the aspect is not discussed, and it does.
- Scores are stored raw (0 to 4) with the five level probabilities and Jev's confidence. Divide by 4 to put them on 0 to 1 before combining aspects.
- The prompt is versioned (`a1`); a change to any wording is a new version and a new run, as with the building questions. The model is pinned to `jev-1.13.0`.

The run is resumable and writes only on the main thread, like the building run. A 200-review pilot came first; the full run followed once the pilot behaved. The cost is a few dollars at Jev's input price, mostly the questions rather than the reviews.

## What was checked

There are **no human labels**, so these are plausibility checks, not accuracy (figures in the private file):

- mention rates differ sensibly by aspect and by star rating (1-star reviews talk about service, not atmosphere);
- among reviews that mention an aspect, the score rises with the review's own stars for every aspect, in the order one would expect, and sits at the middle level where it is not mentioned;
- **Jev's confidence carries information** for food, atmosphere and service (answers it is sure about agree better with the star rating) and **none for value**, so do not gate value on confidence;
- the aspects say something the stars do not: a large share of 4 to 5 star reviews are negative on value, and many 1 to 2 star reviews are positive on atmosphere;
- at place level the aspects separate (value is nearly independent of the rest, atmosphere sits between), while food and service move closely together;
- I read a sample of reviews next to their answers. They matched, apart from the hotel case above.

## What this does not show

- **Accuracy.** Whether Jev scores a given review the way a person would is untested. The roadmap's evaluation (about 500 reviews labelled by hand for the four aspects, then the baseline model and the Jev cascade compared on them) is the real test and needs those labels.
- **Whether food and service really move together or the scorer lets overall tone leak into each aspect (a halo).** Only human labels can tell the two apart.
- **That Jev's scores are better than a simple baseline.** A fine-tuned model or even a star-rating baseline has not been compared.
- **Coverage.** Most of the reviews belong to one area (Rittenhouse), the data stops in January 2022, and Yelp reviewers are a self-selected group.

## Next

1. **Labelling guidelines and a labelled set** of about 500 reviews (stratified by stars and kind of place), scoring each aspect or marking it not mentioned. This is the owner's time; a labelling page like the building review page would make it quicker, and pre-filling from Jev would make it faster still but would bias the labels toward Jev, so it should be an option the labeller can turn off.
2. A baseline model and the cascade comparison on that set.
3. The place-level rating: Bayesian shrinkage with recency weighting over the aspect scores (the roadmap's Week 5), where a place with few reviews should not outrank one with many.
