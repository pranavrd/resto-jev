# 0019: Linking census places to Yelp businesses

- **Status:** Accepted
- **Date:** 2026-10-04
- **Code:** `ingest/yelp.py`, `yelp_match.py` (13 unit tests on invented data), migration 017 (`yelp_business`, `yelp_link`, `yelp_alias`, view `yelp_link_usable`)
- **Results are private.** Numbers and examples derived from the Yelp Data are in `docs/private/yelp-match-results.md` (gitignored; agreement sections 4E and 5, decision 0001). This record covers method and caveats only.
- **Reproduce:** extract the business file from the dataset into `data/yelp/` (gitignored), then `.venv/bin/python -m streetwalker.ingest.yelp` and `.venv/bin/python -m streetwalker.yelp_match [--report]`. `census_area` re-links automatically when it rebuilds `place`.

## What was built

Only the Philadelphia businesses are loaded into the local database (the raw file and the rest of the dataset stay outside git). Each census place is linked to at most one Yelp food or drink business, and each business to at most one place, by greedy one-to-one matching on a score. A link carries its score, what it rests on (`basis`), the name similarity, the distance and a confidence tier.

**Name similarity** compares *distinctive* tokens: legal words (LLC, Inc, Group), venue words (bar, cafe, pizza, sushi, taproom, ...) and area words (Rittenhouse, Passyunk) are dropped, digits become words ("20" and "Twenty"), and the whole name is used when nothing distinctive is left. So "Blue Heron Cafe" and "Blue Heron Taproom" are the same name, "Kobe sushi bar" and "Yoshi Sushi Bar" are not, and "Q KITCHEN + BAR" can still find "q.kitchen". The place's own name wins a tie against a trade name read out of an operator's licence.

**Evidence combined:** the name, a street address that falls in the place's address range (licence range or OSM house number) on the same street, the building both fall in, and distance. Candidates are within 60 m; up to 200 m only when the street address also agrees; up to 150 m for a name that is unique among Philadelphia's Yelp food listings and matches well (a chain name needs the address or building).

**Tiers:**
- **high:** a strong name plus the address or the building (or a very strong name within 40 m);
- **medium:** a good name plus the address, building or closeness, capped at medium when only an operator's licence names the Yelp business (a successor or multi-venue licence) or when only a unique name, far away, supports it;
- **low:** the address and building agree but the names do not.

**Use the view `yelp_link_usable`** (high and medium), never `yelp_link`. Low links are mostly the same storefront with a different business: a place licensed in 2026 and a Yelp listing from 2021 at one address are often different businesses. They are stored so the pattern is visible, and excluded so they cannot attach the wrong reviews. Duplicate Yelp listings of a linked business (same name, same address) are attached in `yelp_alias`.

## How it was checked, and what that does not prove

There is no independent ground truth for these links. I read pairs by hand, as for the census: random samples of the high tier, every medium and low pair, every high pair that rests on a name contained in a longer one, and the places left unlinked next to their closest Yelp candidates. That found three real problems that were fixed: venue words shared by two different businesses counted as a name match; the census scorer reduced a name made of generic words to a single letter, so its best match was lost; and a venue inside a hotel could link to the hotel listing through the hotel operator's licence. **The thresholds and rules were set by looking at the same pairs they are judged on**, so the precision I read off them is optimistic, and a second reader or a held-out sample would be the real test. The results file states the figures and the sampling.

## Caveats that shape any use of the links

- **The snapshot is old.** The Yelp business file is from January 2022; the census describes 2026. A place first licensed after the snapshot cannot be in it, businesses close and change hands, and Yelp's open flag is as of 2022. The match rate has to be read among places that could be in the snapshot (the licence's first-issue date says which), and the results file does this.
- **Same address does not mean same business.** That is why a link needs the names to agree.
- **Reviews can describe a predecessor.** A successor business at the same address, or a renamed one, can inherit the old listing. The tiers cap the clearest cases; they cannot catch all.
- **Coverage is one-sided.** Yelp businesses with no place are not evidence the census misses them: most will have closed, some are not restaurants. This step does not measure census completeness.
- **No Yelp data is exposed.** The search API and the map UI read no Yelp table; a test enforces that the API returns no Yelp, rating or review field. Anything later that shows Yelp-derived content needs the checks listed in decision 0001 first.
- **The Data has a term.** It ends 2027-10-03 (decision 0001); the tables built here are derived data and go with it.

## Next

Reviews for the usable links (the largest file in the dataset, not extracted yet), then aspect scoring. Processing review text with a hosted service rests on the owner's reading of the agreement (decision 0001); the wording difference between the two versions is recorded there.
