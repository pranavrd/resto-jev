"""Link census places to Yelp businesses (decision 0019).   Usage: .venv/bin/python -m streetwalker.yelp_match [--report]

PRIVATE: reads and writes Yelp Data (tables yelp_business, yelp_link). Output stays on this machine.

A Yelp business has a trade name and a street address; a place has an OSM name, a licensed name that may be a legal name
with the trade name in parentheses, a licence address range and a building. The scorer reuses the census pieces (name
similarity with legal words stripped, address ranges) and adds the Yelp address. One Yelp business links to at most one
place and the reverse. Only the pure functions are unit-tested; the data never enters the tests.
"""

import argparse
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from psycopg.rows import tuple_row

from streetwalker import db
from streetwalker.census import _LEGAL, name_variants, parse_address_range
from streetwalker.frontage import name_keys

MAX_DIST_M = 60.0  # Yelp points are less exact than licence points: some sit at the street edge of the lot
FAR_DIST_M = 200.0  # beyond MAX_DIST_M only when the name and the street address both agree
UNIQUE_NAME_DIST_M = 150.0  # or when the name is unique in the city and matches well
MIN_SCORE = 0.45
NEAR_BUILDING_M = 15.0


@dataclass(frozen=True)
class YPlace:
    id: int
    names: list[str]  # every name the place goes by: its own name and the licence's names and trade names
    x: float  # EPSG:32618 metres
    y: float
    building_id: int | None
    addresses: list[tuple[int, int, str]] = field(default_factory=list)  # (first number, last number, street) the place is known at
    own_name: str | None = None  # the name the place itself carries (OSM name, else the licence business name)


@dataclass(frozen=True)
class YBiz:
    id: str
    name: str
    address: str | None
    x: float
    y: float
    building_id: int | None
    is_open: bool = True
    review_count: int = 0
    name_count: int = 1  # Yelp food businesses in Philadelphia with this distinctive name (1 = unique; a chain has many)


@dataclass(frozen=True)
class YMatch:
    place_idx: int
    biz_idx: int
    score: float
    basis: str
    name_sim: float
    dist_m: float
    confidence: str


# Words that describe the kind of venue rather than which venue it is. Two names that differ only in these are the same
# name ("Blue Heron Cafe" and "Blue Heron Taproom"), and two that share only these are not ("Kobe sushi bar", "Yoshi Sushi Bar").
_VENUE_WORDS = {
    "sushi", "pizza", "pizzeria", "pub", "tavern", "taproom", "bistro", "ristorante", "trattoria", "osteria", "coffee", "bakery",
    "deli", "grille", "house", "steakhouse", "steaks", "steak", "thai", "chinese", "mexican", "italian", "indian", "cantina",
    "brewery", "brewing", "lounge", "eatery", "market", "shop", "juice", "tea", "gelato", "creamery", "bagels", "bagel", "wine",
    "beer", "south", "philly", "rittenhouse", "passyunk", "avenue", "street",
}
_NUMBER_WORDS = {str(n): w for n, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"])}


def _tokens(name: str) -> list[str]:
    return [_NUMBER_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", name.lower())]


def distinct_name(name: str) -> str:
    """The part of a name that says which business it is. Falls back to the whole name when nothing distinctive is left."""
    words = _tokens(name)
    core = "".join(w for w in words if w not in _LEGAL and w not in _VENUE_WORDS)
    return core if len(core) >= 2 else "".join(words)


def name_sim(biz_name: str | None, place_names: list[str]) -> float:
    """0 to 1: best match between a Yelp name and any name the place goes by, on distinctive tokens."""
    if not biz_name:
        return 0.0
    a = distinct_name(biz_name)
    best = 0.0
    for n in place_names:
        b = distinct_name(n)
        if not a or not b:
            continue
        ratio = SequenceMatcher(None, a, b).ratio()
        short, long_ = (a, b) if len(a) <= len(b) else (b, a)
        if len(short) >= 4 and short in long_:
            ratio = max(ratio, 0.9)
        best = max(best, ratio)
    return best


def yelp_address(address: str | None) -> tuple[int, int, str] | None:
    """'1616 Chapala St, Ste 2' -> (1616, 1616, 'Chapala St'): the street part only, suite after the comma dropped."""
    if not address:
        return None
    return parse_address_range(address.split(",")[0])


def address_hit(addresses: list[tuple[int, int, str]], biz_address: str | None) -> bool:
    """The Yelp street number lies inside a number range the place is known at, on the same street."""
    biz = yelp_address(biz_address)
    if not biz:
        return False
    lo, hi, street = biz
    keys = name_keys(street)
    return any(plo <= hi and lo <= phi and bool(keys & name_keys(pstreet)) for plo, phi, pstreet in addresses)


def place_addresses(licence_address: str | None, housenumber: str | None, street: str | None) -> list[tuple[int, int, str]]:
    """Every (numbers, street) the place is known at: its licence address range and its OSM house number."""
    out = []
    parsed = parse_address_range(licence_address)
    if parsed:
        out.append(parsed)
    if housenumber and street and (m := re.match(r"\d+", housenumber.strip())):
        n = int(m.group())
        out.append((n, n, street))
    return out


def confidence(sim: float, addr: bool, same_b: bool, d: float) -> str:
    if (sim >= 0.8 and (addr or same_b)) or (sim >= 0.9 and d <= 40):
        return "high"
    if sim >= 0.6 and (addr or same_b or d <= 30):
        return "medium"
    return "low"  # an address or a building agrees but the names do not: usually a different business in the same storefront


def _score(p: YPlace, b: YBiz, only_here: bool) -> tuple[float, str, float, float]:
    d = math.hypot(p.x - b.x, p.y - b.y)
    same_b = p.building_id is not None and p.building_id == b.building_id
    if d > FAR_DIST_M or (d > MAX_DIST_M and not same_b and not address_hit(p.addresses, b.address) and not (b.name_count == 1 and d <= UNIQUE_NAME_DIST_M)):
        return 0.0, "", 0.0, d
    sim_own = name_sim(b.name, [p.own_name]) if p.own_name else 0.0
    sim_any = name_sim(b.name, p.names)
    sim = max(sim_own, 0.97 * sim_any)  # the place's own name wins a tie against a name found in a licence
    licence_only = bool(p.own_name) and sim_own < 0.5 and sim_any >= 0.8  # only the operator's licence names the Yelp business
    addr = address_hit(p.addresses, b.address)
    score = 0.55 * sim + 0.30 * addr + 0.15 * max(0.0, 1 - d / MAX_DIST_M) + 0.15 * same_b + (0.2 if (same_b and only_here) else 0.0)
    parts = [k for k, ok in (("name", sim >= 0.6), ("address", addr), ("building", same_b)) if ok]
    basis = "+".join(parts) if parts else "proximity"
    if licence_only:
        basis += " (licence name only)"
    if same_b and only_here and sim < 0.6 and not addr:
        basis = "building 1:1 (names differ)"
    qualifies = sim >= 0.6 or addr or (same_b and only_here)  # a match needs something beyond closeness
    far = d > MAX_DIST_M and not same_b
    if far and not addr and not (b.name_count == 1 and sim >= 0.9):
        qualifies = False  # a far point needs the address, or a strong and unique name
    if far and addr and sim < 0.8:
        qualifies = False
    if far and not addr:
        basis = "name (unique in the city, far)"
    return (min(score, 1.0) if qualifies else 0.0), basis, sim, d


def match(places: list[YPlace], businesses: list[YBiz]) -> list[YMatch]:
    """One-to-one greedy matching by score. A building with exactly one place and one Yelp food business gets a bonus."""
    p_per_b, y_per_b = Counter(p.building_id for p in places if p.building_id is not None), Counter(b.building_id for b in businesses if b.building_id is not None)
    cands = []
    for i, p in enumerate(places):
        for j, b in enumerate(businesses):
            only = p.building_id is not None and p_per_b[p.building_id] == 1 and y_per_b.get(b.building_id or -1) == 1
            s, basis, sim, d = _score(p, b, only)
            if s >= MIN_SCORE:
                cands.append((s, i, j, basis, sim, d))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_p, used_b, out = set(), set(), []
    for s, i, j, basis, sim, d in cands:
        if i in used_p or j in used_b:
            continue
        used_p.add(i)
        used_b.add(j)
        addr = address_hit(places[i].addresses, businesses[j].address)
        same_b = places[i].building_id is not None and places[i].building_id == businesses[j].building_id
        conf = confidence(sim, addr, same_b, d)
        if "licence name only" in basis and conf == "high":
            conf = "medium"  # successor or multi-venue licence: the identity is ambiguous
        if "unique in the city" in basis:
            conf = "medium"  # a distinctive name alone, with no address or building to confirm it
        out.append(YMatch(i, j, s, basis, sim, d, conf))
    return out


def load(conn) -> tuple[list[YPlace], list[int], list[YBiz], list[dict]]:
    """Places (with their ids), and Yelp food businesses within 100 m of a survey area."""
    cur = conn.cursor(row_factory=tuple_row)
    places, ids = [], []
    for pid, name, lname, addr, x, y, bid, tags in cur.execute(
        """
        SELECT p.id, p.name, p.licence_name, p.address, ST_X(q.pt), ST_Y(q.pt), p.building_id,
               coalesce((SELECT o.tags FROM osm_poi o WHERE o.area_id = p.area_id AND o.osm_type = p.osm_type AND o.osm_id = p.osm_id LIMIT 1),
                        (SELECT o.tags FROM osm_building o WHERE o.area_id = p.area_id AND o.osm_type = p.osm_type AND o.osm_id = p.osm_id LIMIT 1), '{}'::jsonb)
        FROM place p CROSS JOIN LATERAL (SELECT ST_Transform(p.geom, 32618) AS pt) q ORDER BY p.id
        """
    ).fetchall():
        names = name_variants(lname, None) + ([name] if name else [])
        places.append(YPlace(pid, names, x, y, bid, place_addresses(addr, tags.get("addr:housenumber"), tags.get("addr:street")), name or lname))
        ids.append(pid)
    counts = Counter(distinct_name(n) for (n,) in cur.execute("SELECT name FROM yelp_business WHERE is_food").fetchall())
    businesses, meta = [], []
    for bid, name, addr, x, y, nb, is_open, reviews, stars, cats, area in cur.execute(
        """
        SELECT y.business_id, y.name, y.address, ST_X(q.pt), ST_Y(q.pt), nb.id, y.is_open, y.review_count, y.stars, y.categories, a.slug
        FROM yelp_business y JOIN area a ON ST_DWithin(y.geom::geography, a.geom::geography, 100)
        CROSS JOIN LATERAL (SELECT ST_Transform(y.geom, 32618) AS pt) q
        LEFT JOIN LATERAL (SELECT id FROM building WHERE area_id = a.id AND ST_DWithin(ST_Transform(geom, 32618), q.pt, %s)
                           ORDER BY geom <-> y.geom LIMIT 1) nb ON true
        WHERE y.is_food ORDER BY y.business_id
        """,
        (NEAR_BUILDING_M,),
    ).fetchall():
        businesses.append(YBiz(bid, name, addr, x, y, nb, bool(is_open), reviews or 0, counts[distinct_name(name)]))
        meta.append({"stars": stars, "categories": cats, "area": area})
    return places, ids, businesses, meta


def find_aliases(matches: list[YMatch], businesses: list[YBiz]) -> list[tuple[int, int]]:
    """(match index, business index) for unlinked Yelp listings that duplicate a linked one: same distinctive name,
    same street address or within 30 m. Only for high and medium links."""
    linked = {m.biz_idx for m in matches}
    out, taken = [], set()
    for mi, m in enumerate(matches):
        if m.confidence == "low":
            continue
        base = businesses[m.biz_idx]
        for j, b in enumerate(businesses):
            if j in linked or j in taken or b.name_count < 2:
                continue
            same_place = math.hypot(base.x - b.x, base.y - b.y) <= 30 or (yelp_address(base.address) and yelp_address(base.address)[:2] == (yelp_address(b.address) or (0, 0))[:2])
            if same_place and distinct_name(b.name) == distinct_name(base.name):
                out.append((mi, j))
                taken.add(j)
    return out


def link_places(conn) -> list[YMatch]:
    """Rebuild yelp_link from the current places. Safe to re-run (census_area calls it after rebuilding place)."""
    places, ids, businesses, _meta = load(conn)
    matches = match(places, businesses)
    conn.execute("DELETE FROM yelp_link")
    conn.execute("DELETE FROM yelp_alias")
    for mi, j in find_aliases(matches, businesses):
        conn.execute("INSERT INTO yelp_alias (place_id, business_id) VALUES (%s, %s)", (ids[matches[mi].place_idx], businesses[j].id))
    for m in matches:
        conn.execute(
            "INSERT INTO yelp_link (place_id, business_id, score, basis, name_sim, dist_m, confidence) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (ids[m.place_idx], businesses[m.biz_idx].id, m.score, m.basis, m.name_sim, m.dist_m, m.confidence),
        )
    return matches


def report(conn) -> None:
    cur = conn.cursor(row_factory=tuple_row)
    n_places = cur.execute("SELECT count(*) FROM place").fetchone()[0]
    rows = cur.execute(
        """
        SELECT a.slug, p.sources, p.kind, l.confidence, l.basis, y.is_open, y.review_count, y.stars
        FROM place p JOIN area a ON a.id = p.area_id
        LEFT JOIN yelp_link l ON l.place_id = p.id LEFT JOIN yelp_business y ON y.business_id = l.business_id
        """
    ).fetchall()
    linked = [r for r in rows if r[3]]
    print(f"{len(linked)} of {n_places} places linked to a Yelp business ({len(linked) / n_places:.0%})")
    print("  by confidence: " + ", ".join(f"{k} {v}" for k, v in Counter(r[3] for r in linked).most_common()))
    print("  by basis: " + ", ".join(f"{k} {v}" for k, v in Counter(r[4] for r in linked).most_common()))
    by_area = defaultdict(lambda: [0, 0])
    for r in rows:
        by_area[r[0]][0] += 1
        by_area[r[0]][1] += bool(r[3])
    print("  by area: " + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(by_area.items())))
    src = defaultdict(lambda: [0, 0])
    for r in rows:
        key = "both sources" if len(r[1]) == 2 else r[1][0] + " only"
        src[key][0] += 1
        src[key][1] += bool(r[3])
    print("  by source: " + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(src.items())))
    kinds = defaultdict(lambda: [0, 0])
    for r in rows:
        kinds[r[2]][0] += 1
        kinds[r[2]][1] += bool(r[3])
    print("  by kind: " + ", ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1][0])))
    print(f"  duplicate Yelp listings attached as aliases: {cur.execute('SELECT count(*) FROM yelp_alias').fetchone()[0]}")
    print(f"  linked businesses: open at the snapshot {sum(bool(r[5]) for r in linked)}, closed {sum(r[5] is False for r in linked)}; "
          f"reviews: median {sorted(r[6] for r in linked)[len(linked) // 2]}, with 20 or more {sum(r[6] >= 20 for r in linked)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="only print the report, do not re-link")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        if not args.report:
            matches = link_places(conn)
            conn.commit()
            print(f"linked {len(matches)} places")
        report(conn)


if __name__ == "__main__":
    main()
