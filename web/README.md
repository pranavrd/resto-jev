# StreetWalker web viewer

React + Vite + deck.gl, with two views switched from the top-left (`#/places` and `#/replay`): the **places map** over the search API, and the **walk replay**.

## Places map

Search and filter the restaurant census and see each place's SEPTA access. Needs the API running (`.venv/bin/uvicorn streetwalker.api:app --port 8000`); Vite proxies `/api` to it.

- **Map:** places coloured by kind; places the filters exclude stay as hollow rings; SEPTA stops coloured by mode (subway, trolley, rail, bus) and sized by weekday service; footprints and streets for the chosen area come from the replay export, so run `export_replay` once or the map shows points only.
- **Filters:** name or address search, area, kind, rail stop within 200/400/800 m, weekday departures within 400 m, which source lists the place, confidence, sort. Every control maps to one `/places` parameter (`src/places/query.ts`, tested).
- **Selecting a place** (list or map; Esc clears) shows its details, nearest stop and rail, routes, a 400 m ring and the stops inside it.
- Text search zooms to its results. Slow answers cannot overwrite newer ones (in-flight requests are aborted).
- No Yelp data or fields (decision 0017).

## Walk replay

React + Vite + deck.gl viewer that replays the survey walk: the walker moves along each street, buildings light up as they are encountered, and clicking a building shows the evidence text Jev is given.

## Run

```bash
.venv/bin/python -m streetwalker.export_replay   # writes web/public/data/*.json from Postgres (gitignored)
cd web && npm install && npm run dev             # http://localhost:5173
```

`npm run build` type-checks and builds, `npm test` runs the replay-clock unit tests. Space toggles play.

## Views
- **Evidence signal:** colour by what OSM tells the walker (business POI, use tag or name, nothing).
- **Land use (ground truth):** colour by the City's land use. Development only; the classifier never sees it. Flipping between the two views shows the gap Tier 0 has to close.

## Notes
- No basemap: streets and footprints are the map, so there is no tile service or key to manage. A Protomaps PMTiles basemap can be added later.
- Data attribution: © OpenStreetMap contributors, City of Philadelphia. Publishing derived OSM data carries ODbL share-alike obligations (decision 0002).
- **Accepted audit findings:** `npm audit` reports denial-of-service advisories in `fflate` and `image-size`, reached through deck.gl's glTF and 3D-tiles loaders. The viewer only loads its own JSON and never parses untrusted zip or image files. `npm audit fix --force` would downgrade deck.gl, which is not a real fix. Revisit before any hosted deployment, ideally by importing only the deck.gl packages in use (which also shrinks the bundle from about 260 kB gzipped).
