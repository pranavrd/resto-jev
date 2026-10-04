"""Restaurant census: resolve OSM food and drink places against City food licences into one list of places.

Pure matching logic; census_area.py supplies the data. A licence says a legal entity may prepare and serve food at an
address; an OSM place says someone mapped a restaurant, cafe or bar. They overlap imperfectly: legal names differ from
trade names, a licence point can sit on a neighbouring building, and each source misses businesses the other has.
"""

import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from streetwalker.frontage import name_keys

_LEGAL = {"llc", "inc", "co", "corp", "company", "ltd", "lp", "dba", "the", "and", "of", "restaurant", "restaurants",
          "holdings", "group", "enterprises", "enterprise", "management", "services", "philadelphia", "phila", "bar",
          "cafe", "grill", "kitchen", "food", "foods"}

MAX_DIST_M = 30.0
MIN_SCORE = 0.45


def _squash(s: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", s.lower()))


def clean_name(s: str) -> str:
    """Letters-only name without legal and generic words, so 'CREME BRULEE II RESTAURANT INC' compares with 'Creme Brulee'."""
    words = [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _LEGAL]
    return "".join(words)


def name_variants(business_name: str | None, legalname: str | None) -> list[str]:
    """Licence names to compare against: the whole name, the legal name, and anything in parentheses (often the trade name)."""
    out: list[str] = []
    for raw in (business_name, legalname):
        if not raw:
            continue
        out.append(raw)
        out += re.findall(r"\(([^)]+)\)", raw)
        out.append(re.sub(r"\([^)]*\)", " ", raw))  # the name with parentheticals removed
    seen, uniq = set(), []
    for n in out:
        c = clean_name(n)
        if len(c) >= 3 and c not in seen:
            seen.add(c)
            uniq.append(n)
    return uniq


def name_similarity(osm_name: str | None, licence_names: list[str]) -> float:
    """0 to 1: the best match between the OSM name and any licence name variant (containment counts for a lot)."""
    if not osm_name:
        return 0.0
    a = clean_name(osm_name) or _squash(osm_name)
    best = 0.0
    for n in licence_names:
        b = clean_name(n) or _squash(n)
        if not a or not b:
            continue
        ratio = SequenceMatcher(None, a, b).ratio()
        short, long_ = (a, b) if len(a) <= len(b) else (b, a)
        if len(short) >= 5 and short in long_:
            ratio = max(ratio, 0.9)
        best = max(best, ratio)
    return best


def parse_address_range(address: str | None) -> tuple[int, int, str] | None:
    """'1709-17 E PASSYUNK AVE' -> (1709, 1717, 'passyunk avenue' key); '1244 SNYDER AVE' -> (1244, 1244, ...)."""
    if not address:
        return None
    m = re.match(r"\s*(\d+)(?:\s*-\s*(\d+))?\s+(.*)", address)
    if not m:
        return None
    lo = int(m.group(1))
    hi = lo
    if m.group(2):
        tail = m.group(2)
        hi = int(str(lo)[: -len(tail)] + tail) if len(tail) < len(str(lo)) else int(tail)
        hi = max(hi, lo)
    return lo, hi, m.group(3)


def address_match(osm_housenumber: str | None, osm_street: str | None, licence_address: str | None) -> bool:
    """Same street and the OSM house number falls inside the licence's number range."""
    parsed = parse_address_range(licence_address)
    if not parsed or not osm_housenumber or not osm_street:
        return False
    num = re.match(r"\d+", osm_housenumber.strip())
    if not num:
        return False
    lo, hi, street = parsed
    return lo <= int(num.group()) <= hi and bool(name_keys(osm_street) & name_keys(street))


def osm_kind(tags: dict) -> str:
    amenity, shop = tags.get("amenity"), tags.get("shop")
    if amenity == "restaurant" or amenity == "food_court":
        return "restaurant"
    if amenity == "fast_food":
        return "fast food"
    if amenity == "cafe" or shop in ("coffee", "tea"):
        return "cafe"
    if amenity in ("bar", "pub", "biergarten"):
        return "bar"
    if amenity == "ice_cream" or shop == "ice_cream":
        return "ice cream"
    if shop in ("bakery", "pastry", "confectionery", "chocolate", "deli"):
        return "bakery or deli"
    return "other food"


@dataclass(frozen=True)
class OsmPlace:
    osm_type: str
    osm_id: int
    name: str | None
    kind: str
    x: float  # metres (projected)
    y: float
    building_id: int | None
    housenumber: str | None = None
    street: str | None = None
    check_date: str | None = None
    has_hours: bool = False


@dataclass(frozen=True)
class Licence:
    id: int
    names: list[str]
    address: str | None
    x: float
    y: float
    building_id: int | None
    licence_type: str


@dataclass(frozen=True)
class Match:
    osm_idx: int
    lic_idx: int
    score: float
    basis: str  # what carried the match
    name_sim: float
    dist_m: float
    flags: list[str] = field(default_factory=list)


def _score(o: OsmPlace, lic: Licence, only_here: bool) -> tuple[float, str, float, float]:
    d = math.hypot(o.x - lic.x, o.y - lic.y)
    if d > MAX_DIST_M and not (o.building_id and o.building_id == lic.building_id):
        return 0.0, "", 0.0, d
    sim = name_similarity(o.name, lic.names)
    same_b = o.building_id is not None and o.building_id == lic.building_id
    addr = address_match(o.housenumber, o.street, lic.address)
    score = 0.45 * sim + 0.25 * same_b + 0.15 * max(0.0, 1 - d / MAX_DIST_M) + 0.5 * addr + (0.2 if (same_b and only_here) else 0.0)
    parts = [p for p, ok in (("name", sim >= 0.6), ("address", addr), ("building", same_b)) if ok]
    basis = "+".join(parts) if parts else "proximity"
    if same_b and only_here and sim < 0.6 and not addr:
        basis = "building 1:1 (names differ)"
    # a match needs something beyond mere closeness
    qualifies = sim >= 0.6 or addr or same_b
    return (min(score, 1.0) if qualifies else 0.0), basis, sim, d


def match_places(osm: list[OsmPlace], licences: list[Licence]) -> list[Match]:
    """One-to-one greedy matching by score. A building holding exactly one OSM place and one licence gets a bonus
    (a restaurant rarely shares a building with another), flagged when the names disagree."""
    osm_per_b: dict[int, int] = {}
    lic_per_b: dict[int, int] = {}
    for o in osm:
        if o.building_id is not None:
            osm_per_b[o.building_id] = osm_per_b.get(o.building_id, 0) + 1
    for lic in licences:
        if lic.building_id is not None:
            lic_per_b[lic.building_id] = lic_per_b.get(lic.building_id, 0) + 1
    cands = []
    for i, o in enumerate(osm):
        for j, lic in enumerate(licences):
            only = o.building_id is not None and osm_per_b.get(o.building_id) == 1 and lic_per_b.get(lic.building_id or -1) == 1
            s, basis, sim, d = _score(o, lic, only)
            if s >= MIN_SCORE:
                cands.append((s, i, j, basis, sim, d))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_o, used_l, out = set(), set(), []
    for s, i, j, basis, sim, d in cands:
        if i in used_o or j in used_l:
            continue
        used_o.add(i)
        used_l.add(j)
        out.append(Match(i, j, s, basis, sim, d))
    return out


def chapman(n1: int, n2: int, m: int) -> tuple[float, float, float]:
    """Capture-recapture estimate of the total (Chapman's unbiased form) with an approximate 95% interval.
    Assumes the two sources find businesses independently, which is violated whenever both miss the same kind of place,
    so it is a rough lower-bound-ish figure, not a measurement."""
    n_hat = (n1 + 1) * (n2 + 1) / (m + 1) - 1
    var = (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2))
    se = math.sqrt(max(var, 0.0))
    return n_hat, n_hat - 1.96 * se, n_hat + 1.96 * se
