# Week 2 (Oct 12–18, started early): the walk

- [x] Street graph per area: full network, undirected, nodes stored, geometry oriented
- [x] Eulerian circuit per component, length-weighted (`src/streetwalker/walk.py`, 17 tests)
- [x] `walk_run` and `walk_step` tables; `python -m streetwalker.walk_area` (decision 0004)
- [x] Integrity checks: full coverage, continuity, orientation
- [ ] Frontage assignment: nearest street segment and side for each building
- [ ] Ordered encounters and the `walk_event` log
- [ ] Evidence bundles: OSM tags, POIs, geometry, neighbour context
- [ ] Replay prototype (deck.gl path layer, buildings lighting up as encountered)

Exit: a replayable walk for each area with an evidence bundle per building.
