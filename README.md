# StreetWalker

A deterministic street survey of three Philadelphia areas. Each building is classified (residential, commercial, restaurant, cafe, and so on) with Jev decisions over OSM tags and geometry, escalating to street imagery and a local vision model only when confidence is low. Its restaurant universe feeds TableMap, a ranking and review-chat layer.

Status: Week 1, setup. See [docs/week1-checklist.md](docs/week1-checklist.md) and [docs/decisions/](docs/decisions/).

## Data policy

Raw data lives in `data/` and is never committed. Yelp data, and anything derived from it, stays private until the Yelp license question in [decision 0001](docs/decisions/0001-yelp-license-and-showcase.md) is resolved.

## Local setup

```bash
cp .env.example .env        # then set a local password
docker compose up -d db
```
