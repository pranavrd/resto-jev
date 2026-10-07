# 0033: The restaurant census against Yelp

- **Status:** Accepted
- **Date:** 2026-10-07
- **Code:** `census_vs_yelp.py` (rules unit-tested on invented businesses in `tests/test_census_vs_yelp.py`)
- **Results are private.** The figures and the names are in `docs/private/census-vs-yelp.md` (gitignored; agreement sections 4E and 5, decision 0001). This record has the method and its limits only.
- **Reproduce:** `.venv/bin/python -m streetwalker.census_vs_yelp --write`

## Question

Decision 0019 linked census places to Yelp businesses and said it did not measure completeness. The roadmap's census also asked how it compares with Yelp. The question here is the reverse of the link rate: of the food and drink businesses Yelp had **open inside the three areas at its snapshot (January 2022)**, how many does the census hold, and what explains the rest?

## Method (no labels, no lookups)

Take the Yelp businesses that were open at the snapshot, are food listings, and sit inside an area. Drop the ones that are not somewhere to eat (grocery, hotel: the dining rule of decision 0020). Of the rest, some have a usable link to a place. For every one **without** a link (a gap), the first explanation that holds, in this order:

| Explanation | Evidence |
|---|---|
| census miss | a "Food Preparing" licence (the type the census is built from) is active today, carries the Yelp name within 60 m, and **no place holds it** |
| other licence | an active licence of a type the census does not use (retail food) carries the name: a gap in the census's *scope* |
| link missed | the census **has** the place (a place holds the licence that carries the Yelp name, or a place within 60 m with a similar name, or within 250 m with the same name) and the matcher did not link it |
| licence ended | a food licence with that name within 60 m is closed, inactive, expired or revoked, or has an inactive date: the business is gone |
| turnover | a place within 25 m, first licensed after the snapshot, has a different name: another business took the spot |
| unexplained | none of the above |

The evidence is the City's licence table, which keeps ended licences with their dates, so closure can be checked without a human and without looking anything up. Recall of the census against Yelp's list is reported as **three bounds**, not one number: every gap against the census (what the matcher proves); the places the census holds over the businesses that can still be there (gaps explained by an ended licence or a replacement are taken out); and the same with "unexplained" also taken as closed. A two-source capture-recapture estimate (Chapman, over the census places that could be on the snapshot and Yelp's list) is given with its assumption stated.

## What this found (aggregates only; details are private)

- **Most gaps are not census holes.** The largest groups are businesses whose licence has ended or whose spot a new business has taken. A real census miss, by the strict test above, was not found: the cases first flagged as misses were places the census does have, which the matcher had not linked (a name inside a legal-entity name, two businesses at one address, or a Yelp point far from the licensed address). **The first version of the analysis called them census misses and was wrong**; checking whether a place holds the licence turned them into missed links.
- **The matcher is the weak part, not the census.** A number of Yelp businesses have a census place that the link step left unlinked. That lowers the usable-link count and is a reason to prefer the licence-based reading to the link-based one when judging completeness.
- **One scope gap:** the census uses "Food Preparing and Serving" licences only, so a market or store that Yelp lists as dining and that holds only a retail-food licence is not in it.
- **A residue is unexplained.** Reading it (as an AI reader, nothing looked up), most are large restaurants that probably closed under a legal name the comparison cannot read, plus non-restaurants; the private report lists the one to check by hand first.

## Limits

- **Yelp is a 2022 list and the census a 2026 one.** The two cannot be compared as snapshots; the licence dates are what bridge them, and a business with no licence under its trade name looks "unexplained" however it ended.
- **Names do the work.** Licences carry legal names, Yelp trade names; the name comparison is the matcher's (decision 0019), whose thresholds were set by looking at the same pairs. A short Yelp name contained in a longer licence name can match by accident.
- **The bounds are wide on purpose.** The generous one assumes every unexplained gap closed, which is optimistic; the pessimistic one counts links the matcher missed against the census, which is unfair to it. The truth is between them, and nothing here says where.
- **Capture-recapture is not a measurement.** Both lists miss the small and the new businesses, so independence fails and the estimate is a floor on what the true number is, not an estimate of it.
- **No independent check.** No gap was verified against the street or the web. That is a deliberate limit (no human labels, no sending Yelp-derived names to third parties).

## Consequences

- The roadmap's "Yelp comparison" item is done at this level of evidence. A stronger answer needs someone to look at the "unexplained" list, which is short, and that is a labelling task the owner has ruled out; it stays as the bound.
- The link matcher could recover the missed links by also accepting a licence-name match (the evidence this analysis used). That would raise the number of places with reviews; it is not done here because it changes what reviews attach to which place, which decision 0019 decided with the tiers.
