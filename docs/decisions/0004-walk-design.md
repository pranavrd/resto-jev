# 0004: Walk design

- **Status:** Accepted
- **Date:** 2026-10-03

## Decisions

| Question | Choice | Why |
|---|---|---|
| Which network is walked? | Street centrelines only: `motorway` through `residential`, `service`, `living_street`, `*_link`. Footways, paths, steps and cycleways are excluded. | Buildings front streets. In Philadelphia the OSM sidewalks are mapped as separate footways, so walking them would roughly double the walk and add crossings without adding frontages. |
| Which OSM pull? | `network_type="all"`, stored as one undirected edge per physical segment. | OSMnx's `walk` filter drops about 200 residential streets in the Roxborough box, leaving houses a median 28 m from any road. With `all`, the median is 10 m. The directed graph also stored each two-way street twice, which made every node look even-degree. |
| How are circuits closed? | Length-weighted minimum matching of odd nodes (Chinese postman), implemented in `walk.py`. | `nx.eulerize` minimises hop count, not metres. On our areas the weighted version has 1.1 to 3.4 points less overhead (Roxborough 1.1, East Passyunk 2.2, Rittenhouse 3.4). A unit test pins the minimal-metres behaviour on a case where a 500 m single hop competes with a 20 m two-hop route. |
| Disconnected components | One circuit per component, visited nearest-first, with an explicit jump step. | A walker cannot cross a gap in the street graph. Jumps are logged (`is_jump`) and measured (Roxborough: one 758 m jump). |
| Start | Westmost node of the largest component; the circuit closes at its start. | Deterministic, and loops cleanly for the replay. |
| Re-walks | Exactly one pass per segment is `is_repeat = false`; every later pass is `true`. | Downstream steps (frontage, encounter order) need to process each segment once and ignore re-walks. |

## Results (2026-10-03)

| Area | Street edges | Street km | Walked km | Overhead | `nx.eulerize` overhead | Components |
|---|---|---|---|---|---|---|
| Rittenhouse | 237 | 9.38 | 13.02 | 38.8% | 42.2% | 1 |
| East Passyunk | 332 | 16.63 | 22.15 | 33.2% | 35.4% | 1 |
| Roxborough | 285 | 13.16 | 20.97 | 59.3% | 60.4% | 2 (one 758 m jump) |

Overhead is mostly dead ends: each service spur and driveway must be retraced. Roxborough is worst (156 of 441 steps are re-walks) because of internal drives and parking aisles.

## Follow-ups
- After frontage assignment, test a **required-edges-only** walk (rural postman): drop segments that no building fronts. This should cut overhead sharply in Roxborough. It is an optimisation, not a prerequisite.
- If a sidewalk-side "which side of the street" signal is needed, derive it from the cross product (as in the roadmap), not from walking sidewalks.
