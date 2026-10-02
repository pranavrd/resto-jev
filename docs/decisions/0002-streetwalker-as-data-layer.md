# 0002: StreetWalker is the data layer; Yelp is a gated layer on top

- **Status:** Accepted
- **Date:** 2026-10-02
- **Supersedes:** the data-ingest and timeline parts of the original TableMap roadmap

## Decision

The project is built in two layers:

1. **StreetWalker (public-safe).** A deterministic street survey of three Philadelphia areas. Buildings are classified with Jev decisions over OSM tags and geometry, escalating to Mapillary imagery plus a local vision model when confidence is low. Sources are OSM, Mapillary and OpenDataPhilly only.
2. **TableMap (gated by the Yelp license).** Restaurant ranking, aspect ratings, hotspots and review RAG chat, built on StreetWalker's restaurant universe joined to Yelp. Treated as private until Yelp consent exists (see 0001).

StreetWalker is the public showcase. TableMap stays local and private unless consent allows more.

## Changes to the original StreetWalker plan

| Change | Why |
|---|---|
| Add a `place` table (OSM POIs + business licenses) alongside `building`. Buildings are containers, places are what get classified as restaurants and matched to Yelp. | A building can hold several businesses, or a cafe plus offices. A single `is_food` flag per building loses that. |
| Yelp match-rate probe moves out of Week 1 and happens when Yelp is first used. | Yelp use is deferred (0001). Area selection in Week 1 uses OSM and license density instead. |
| Gi* hotspots are citywide from Yelp alone, or demoted to exploratory. | Three small disjoint areas are too thin for spatial statistics. |
| Walk is described as a deterministic traversal with a confidence-gated cascade, not an "agent". | Accurate, and the neighbor-context ablation tests whether order helps. |
| Restaurant census headline is vs business licenses. The Yelp diff is separate and private or pre-approved. | Yelp metrics fall under §3/§4E of the Yelp terms. |

## Attribution and license notes

- **OSM (ODbL):** attribute; a publicly shared derived database carries share-alike obligations.
- **Mapillary:** images are CC BY-SA 4.0. Cache image IDs and captions, not images. Attribute if images are shown.
- **OpenDataPhilly:** check each dataset's terms when ingested; record them in `docs/data-sources.md`.

## Week 1 order (no Yelp)

1. Mapillary coverage per candidate area.
2. Parcel and business-license fields and update dates.
3. Lock the three areas, using building/POI density and Mapillary coverage.
4. Repo, Docker Compose, Postgres + PostGIS + pgvector (this commit).
5. Ingest OSM and city data.
