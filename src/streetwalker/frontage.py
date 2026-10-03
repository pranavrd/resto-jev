"""Assign each building to the street segment it fronts, with side and position along the segment.

Pure geometry: inputs are projected (metres) shapes. Rules, in order:
  1. Candidates are street segments within SEARCH_M of the footprint (else the nearest one overall).
  2. If the building has an address and a candidate carries that street name, take the nearest such.
  3. Otherwise take the nearest candidate, but prefer a non-service road over a service road (rear
     alley, driveway) when one lies within SERVICE_SLACK_M of it.
The side comes from the cross product of the segment direction and the vector to the building.
"""

import json
import re
from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

SEARCH_M = 40.0
SERVICE_SLACK_M = 15.0

_ABBREV = {
    "st": "street", "ave": "avenue", "av": "avenue", "rd": "road", "blvd": "boulevard", "dr": "drive",
    "ln": "lane", "pl": "place", "ct": "court", "ter": "terrace", "sq": "square", "pkwy": "parkway",
    "n": "north", "s": "south", "e": "east", "w": "west",
}
_DIRECTIONS = {"north", "south", "east", "west"}


def norm_street(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(_ABBREV.get(t, t) for t in tokens)


def _strip_direction(norm: str) -> str:
    return " ".join(t for t in norm.split() if t not in _DIRECTIONS)


def name_keys(raw: str | None) -> frozenset[str]:
    """Match keys for a street name: the normalised name, and the name without directional words.
    Accepts a plain name or a JSON list (OSMnx merges tags)."""
    if not raw:
        return frozenset()
    names = json.loads(raw) if raw.startswith("[") else [raw]
    keys = set()
    for n in names:
        nn = norm_street(n)
        if nn:
            keys.add(nn)
            keys.add(_strip_direction(nn))
    return frozenset(keys)


@dataclass(frozen=True)
class EdgeInfo:
    geom: LineString
    keys: frozenset[str]
    is_service: bool


@dataclass(frozen=True)
class BuildingInfo:
    geom: BaseGeometry
    addr_street: str | None


@dataclass(frozen=True)
class Frontage:
    edge_idx: int
    side: int  # +1: building is left of the segment's stored direction (u -> v), -1: right
    dist_m: float
    along_m: float  # position of the footprint centroid projected onto the stored geometry, from u
    frac: float
    method: str  # address | nearest | nearest_nonservice | nearest_far
    n_candidates: int
    margin_m: float | None  # gap to the nearest candidate on a different non-service street; small means a corner
    nearest_same: bool  # would plain nearest-segment have chosen the same street
    frontage_xy: tuple[float, float]


def _same_street(a: EdgeInfo, b: EdgeInfo) -> bool:
    return bool(a.keys & b.keys)


def assign_frontage(b: BuildingInfo, edges: list[EdgeInfo], tree: STRtree) -> Frontage:
    cand = [int(i) for i in tree.query(b.geom, predicate="dwithin", distance=SEARCH_M)]
    far = not cand
    if far:
        cand = [int(tree.nearest(b.geom))]
    dist = {i: edges[i].geom.distance(b.geom) for i in cand}
    nearest = min(cand, key=lambda i: (dist[i], i))

    chosen, method = nearest, "nearest_far" if far else "nearest"
    keys = name_keys(b.addr_street)
    matching = [i for i in cand if keys & edges[i].keys] if keys else []
    if matching:
        chosen, method = min(matching, key=lambda i: (dist[i], i)), "address"
    elif edges[nearest].is_service and not far:
        better = [i for i in cand if not edges[i].is_service and dist[i] <= dist[nearest] + SERVICE_SLACK_M]
        if better:
            chosen, method = min(better, key=lambda i: (dist[i], i)), "nearest_nonservice"

    # a corner means another real street is nearly as close; alleys and driveways don't count
    others = [
        i for i in cand if i != chosen and not edges[i].is_service and not _same_street(edges[i], edges[chosen])
    ]
    margin = min(dist[i] for i in others) - dist[chosen] if others else None

    line = edges[chosen].geom
    # Position and side come from the footprint's centroid (representative point if the centroid falls
    # outside, e.g. a courtyard building). The nearest footprint point is arbitrary for a facade that
    # runs parallel to the street, which would make the encounter order noisy.
    centre = b.geom.centroid if b.geom.contains(b.geom.centroid) else b.geom.representative_point()
    along = line.project(centre)
    foot = line.interpolate(along)
    frontage_pt = nearest_points(b.geom, foot)[0]
    ahead, behind = line.interpolate(min(along + 1.0, line.length)), line.interpolate(max(along - 1.0, 0.0))
    dx, dy = ahead.x - behind.x, ahead.y - behind.y
    cross = dx * (centre.y - foot.y) - dy * (centre.x - foot.x)
    return Frontage(
        edge_idx=chosen,
        side=1 if cross >= 0 else -1,
        dist_m=dist[chosen],
        along_m=along,
        frac=along / line.length if line.length else 0.0,
        method=method,
        n_candidates=len(cand),
        margin_m=margin,
        nearest_same=chosen == nearest or _same_street(edges[chosen], edges[nearest]),
        frontage_xy=(frontage_pt.x, frontage_pt.y),
    )


def assign_all(buildings: list[BuildingInfo], edges: list[EdgeInfo]) -> list[Frontage]:
    tree = STRtree([e.geom for e in edges])
    return [assign_frontage(b, edges, tree) for b in buildings]
