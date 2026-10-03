# Week 2 (Oct 12–18, started early): the walk

- [x] Street graph per area: full network, undirected, nodes stored, geometry oriented
- [x] Eulerian circuit per component, length-weighted (`src/streetwalker/walk.py`, 17 tests)
- [x] `walk_run` and `walk_step` tables; `python -m streetwalker.walk_area` (decision 0004)
- [x] Integrity checks: full coverage, continuity, orientation
- [x] Frontage assignment: segment, side and position per building (`building` table, decision 0005, 16 tests)
- [x] Ordered encounters and the `walk_event` log (one per building, verified)
- [x] Evidence bundles v1: OSM tags, POIs, geometry, neighbour context (decision 0006, 20 tests, signal audit)
- [x] Replay prototype (`web/`: deck.gl trail, walked streets, buildings lighting up, click for evidence; 60 fps on 2,548 buildings)

Exit: a replayable walk for each area with an evidence bundle per building.

**Week 2 exit met 2026-10-03:** a replayable walk for each area with an evidence bundle per building.
