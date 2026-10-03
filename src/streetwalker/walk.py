"""Deterministic street walk: one Eulerian circuit per connected component of the street graph.

Every street segment is walked at least once. Segments that must be re-walked to close the circuit
are chosen by a length-weighted Chinese-postman matching (not networkx's hop-count `eulerize`, which
can pick longer detours). The planner is pure: it takes edges and node coordinates and returns steps.
"""

import json
import math
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

import networkx as nx

# highway values that count as streets. Footways, paths, steps and cycleways are sidewalks and
# trails, not frontages; buildings are assigned to street centrelines.
STREET_TYPES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "living_street", "service", "road",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}


def is_street(highway: str | None) -> bool:
    """highway may be a plain tag or a JSON list (OSMnx merges tags); any street value qualifies."""
    if not highway:
        return False
    values = json.loads(highway) if highway.startswith("[") else [highway]
    return any(v in STREET_TYPES for v in values)


@dataclass(frozen=True)
class StreetEdge:
    u: int
    v: int
    k: int
    length_m: float


@dataclass(frozen=True)
class Step:
    seq: int
    component: int
    u: int  # walked from u ...
    v: int  # ... to v
    edge_idx: int  # index into the input edge list
    is_repeat: bool
    is_jump: bool  # True on the first step of a component reached by teleport
    length_m: float


@dataclass(frozen=True)
class WalkPlan:
    steps: list[Step]
    n_components: int
    street_m: float
    walked_m: float
    naive_walked_m: float
    jump_m: float
    n_jumps: int

    @property
    def repeat_m(self) -> float:
        return self.walked_m - self.street_m

    @property
    def overhead_pct(self) -> float:
        return 100 * self.repeat_m / self.street_m if self.street_m else 0.0


def _dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate metres between two (lng, lat) points; fine at neighbourhood scale."""
    dy = (b[1] - a[1]) * 111_320
    dx = (b[0] - a[0]) * 111_320 * math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot(dx, dy)


def _simple_projection(g: nx.MultiGraph) -> nx.Graph:
    """Collapse parallel edges to the shortest, remembering which one it was."""
    s = nx.Graph()
    for a, b, key, data in g.edges(keys=True, data=True):
        if a == b:
            continue
        if not s.has_edge(a, b) or data["length"] < s[a][b]["length"]:
            s.add_edge(a, b, length=data["length"], eid=data["eid"], key=key)
    return s


def _eulerize(comp: nx.MultiGraph) -> nx.MultiGraph:
    """Add the minimum total length of duplicate edges so every node has even degree."""
    h = nx.MultiGraph(comp)
    odd = [n for n, d in h.degree() if d % 2]
    if not odd:
        return h
    s = _simple_projection(comp)
    dist, path = {}, {}
    for n in odd:
        dist[n], path[n] = nx.single_source_dijkstra(s, n, weight="length")
    pairs = nx.Graph()
    for i, a in enumerate(odd):
        for b in odd[i + 1 :]:
            pairs.add_edge(a, b, weight=dist[a][b])
    for a, b in nx.min_weight_matching(pairs):
        p = path[a][b]
        for x, y in pairwise(p):
            e = s[x][y]
            h.add_edge(x, y, eid=e["eid"], length=e["length"], dup=True)
    return h


def _naive_extra_m(comp: nx.MultiGraph) -> float:
    """Extra length networkx's hop-count eulerize would add. Baseline for the overhead metric."""
    shortest = _simple_projection(comp)

    def counts(g: nx.MultiGraph) -> Counter:
        return Counter((min(a, b), max(a, b)) for a, b in g.edges() if a != b)

    before, after = counts(comp), counts(nx.eulerize(nx.MultiGraph(comp)))
    return sum(
        extra * shortest[a][b]["length"] for (a, b), n in after.items() if (extra := n - before[(a, b)]) > 0
    )


def plan_walk(edges: list[StreetEdge], node_xy: dict[int, tuple[float, float]]) -> WalkPlan:
    """Plan a deterministic walk covering every edge. node_xy maps node id -> (lng, lat)."""
    g = nx.MultiGraph()
    for idx, e in enumerate(edges):
        g.add_edge(e.u, e.v, key=idx, eid=idx, length=e.length_m, dup=False)

    comps = [g.subgraph(c).copy() for c in nx.connected_components(g)]
    comps.sort(key=lambda c: (-c.size(weight="length"), min(c.nodes)))  # largest first, deterministic

    def total(c: nx.MultiGraph) -> float:
        return c.size(weight="length")

    steps: list[Step] = []
    walked = naive_extra = jump_m = 0.0
    n_jumps = 0
    remaining = list(range(len(comps)))
    pos: tuple[float, float] | None = None
    comp_no = 0
    while remaining:
        if pos is None:
            pick = remaining[0]
            start = min(comps[pick].nodes, key=lambda n: (node_xy[n][0], node_xy[n][1], n))  # westmost node
            jumped = False
        else:  # nearest remaining component to where the last circuit ended
            pick, start = min(
                ((ci, n) for ci in remaining for n in comps[ci].nodes),
                key=lambda t: (_dist_m(pos, node_xy[t[1]]), t[1]),
            )
            jump_m += _dist_m(pos, node_xy[start])
            n_jumps += 1
            jumped = True
        remaining.remove(pick)
        comp = comps[pick]
        euler = _eulerize(comp)
        naive_extra += _naive_extra_m(comp)
        assert nx.is_eulerian(euler)
        seen_eids: set[int] = set()
        first = True
        for a, b, key in nx.eulerian_circuit(euler, source=start, keys=True):
            data = euler.edges[a, b, key]
            repeat = data["eid"] in seen_eids  # exactly one non-repeat pass per segment
            seen_eids.add(data["eid"])
            steps.append(
                Step(len(steps), comp_no, a, b, data["eid"], repeat, jumped and first, data["length"])
            )
            walked += data["length"]
            first = False
        pos = node_xy[start]  # a circuit ends where it began
        comp_no += 1

    street_m = sum(e.length_m for e in edges)
    return WalkPlan(steps, len(comps), street_m, walked, street_m + naive_extra, jump_m, n_jumps)
