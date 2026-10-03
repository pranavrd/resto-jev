"""Tier 0 evidence bundle for a building: cheap, text-renderable facts for Jev and the baselines.

Sources are OSM tags, OSM POIs, footprint geometry, the street it fronts and walk-order context.
Never parcels, land use or licences: those are the ground truth the classifier is scored against
(a test enforces that this module and its runner do not touch them).
"""

import math
from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

BUNDLE_VERSION = "v1"
NEAR_POI_M = 10.0  # a POI mapped outside every footprint is linked to a building at most this far away
PARTY_WALL_TOL_M = 0.25  # footprints drawn this close count as touching (party walls are often drawn with a gap)
PARTY_WALL_MIN_M = 2.0  # shared boundary length for two footprints to count as attached; the tolerance
# overshoots each wall end by up to PARTY_WALL_TOL_M, so a corner-only touch stays below this

# Amenities that are street furniture or infrastructure: not businesses, so not evidence about use.
FURNITURE = {
    "bench", "bicycle_parking", "waste_basket", "post_box", "bicycle_rental", "vending_machine",
    "car_sharing", "public_bookcase", "parking", "parking_space", "parking_entrance", "charging_station",
    "drinking_water", "telephone", "recycling", "shelter", "clock", "bicycle_repair_station",
    "waste_disposal", "fountain", "atm", "toilets", "motorcycle_parking", "scooter_rental", "post_office_box",
    "loading_dock", "give_box", "lounger", "table", "device_charging_station", "bbq", "dog_toilet",
}
BUSINESS_KEYS = ("amenity", "shop", "office", "craft", "tourism", "healthcare", "leisure")
# Tag values under a business key that are public space, not a business.
NON_BUSINESS = {
    "tourism": {"artwork", "information", "viewpoint", "picnic_site"},
    "leisure": {"park", "playground", "pitch", "garden", "picnic_table", "dog_park", "fitness_station", "track"},
}
POI_KEEP = (
    "name", "amenity", "shop", "office", "craft", "tourism", "healthcare", "leisure", "cuisine", "brand",
    "operator", "takeaway", "delivery", "outdoor_seating", "diet:vegan", "diet:vegetarian", "religion",
    "denomination", "sport",
)
BUILDING_USE_KEYS = (*BUSINESS_KEYS, "religion", "historic")


def _float(v: object) -> float | None:
    try:
        return float(str(v).split()[0])
    except (ValueError, IndexError):
        return None


def is_business_poi(tags: dict) -> bool:
    """True when the tags describe something that operates at a place, not furniture or public space."""
    for key in BUSINESS_KEYS:
        if key not in tags:
            continue
        if key == "amenity" and tags[key] in FURNITURE:
            continue
        if tags[key] in NON_BUSINESS.get(key, ()):
            continue
        return True
    return False


def poi_summary(tags: dict) -> dict:
    out = {k: tags[k] for k in POI_KEEP if k in tags}
    for flag in ("opening_hours", "website", "phone"):
        if flag in tags or f"contact:{flag}" in tags:
            out[f"has_{flag}"] = True
    return out


def building_osm(tags: dict) -> dict:
    """What OSM itself says about the building. Address *street* is omitted (it is the fronted street)."""
    out: dict = {"building": tags.get("building", "yes")}
    if (v := _float(tags.get("building:levels"))) is not None:
        out["levels"] = int(v) if v == int(v) else v
    if (v := _float(tags.get("height"))) is not None:
        out["height_m"] = round(v, 1)
    for tag_key, out_key in (("name", "name"), ("building:material", "material"), ("roof:shape", "roof_shape")):
        if tag_key in tags:
            out[out_key] = tags[tag_key]
    if "addr:housenumber" in tags:
        out["housenumber"] = tags["addr:housenumber"]
    if "addr:unit" in tags:
        out["has_unit"] = True
    use = {k: tags[k] for k in BUILDING_USE_KEYS if k in tags}
    if use:
        out["use_tags"] = use
        for extra in ("cuisine", "brand", "operator"):
            if extra in tags:
                out["use_tags"][extra] = tags[extra]
    return out


@dataclass(frozen=True)
class PoiLink:
    poi_idx: int
    building_idx: int
    match: str  # contained | nearby
    dist_m: float


def link_pois(buildings: list[BaseGeometry], pois: list[BaseGeometry]) -> list[PoiLink]:
    """Link each POI to one building: the smallest footprint containing it, else the nearest within
    NEAR_POI_M. POIs that no building is near are left unlinked."""
    if not buildings:
        return []
    tree = STRtree(buildings)
    links = []
    for pi, poi in enumerate(pois):
        pt = poi if isinstance(poi, Point) else poi.representative_point()
        inside = [int(i) for i in tree.query(pt, predicate="within")]
        if inside:
            bi = min(inside, key=lambda i: (buildings[i].area, i))
            links.append(PoiLink(pi, bi, "contained", 0.0))
            continue
        near = [int(i) for i in tree.query(pt, predicate="dwithin", distance=NEAR_POI_M)]
        if near:
            bi = min(near, key=lambda i: (buildings[i].distance(pt), i))
            links.append(PoiLink(pi, bi, "nearby", buildings[bi].distance(pt)))
    return links


def shared_walls(buildings: list[BaseGeometry]) -> list[tuple[int, float]]:
    """(number of attached neighbours, share of the perimeter that is party wall) per building."""
    tree = STRtree(buildings)
    out = []
    for i, b in enumerate(buildings):
        n, shared = 0, 0.0
        for j in tree.query(b.buffer(0.5)):
            if int(j) == i:
                continue
            length = b.boundary.intersection(buildings[int(j)].buffer(PARTY_WALL_TOL_M)).length
            if length >= PARTY_WALL_MIN_M:
                n += 1
                shared += length
        perimeter = b.length
        out.append((n, min(1.0, shared / perimeter) if perimeter else 0.0))
    return out


def geometry_features(geom: BaseGeometry, street: LineString, along_m: float, dist_m: float) -> dict:
    """Footprint shape in a street-aligned frame: width runs along the street, depth away from it."""
    area, perimeter = geom.area, geom.length
    here = street.interpolate(max(along_m - 1.0, 0.0))
    there = street.interpolate(min(along_m + 1.0, street.length))
    dx, dy = there.x - here.x, there.y - here.y
    norm = math.hypot(dx, dy) or 1.0
    tx, ty = dx / norm, dy / norm
    pts = list(geom.convex_hull.exterior.coords)
    along = [x * tx + y * ty for x, y in pts]
    across = [-x * ty + y * tx for x, y in pts]
    width, depth = max(along) - min(along), max(across) - min(across)
    return {
        "area_m2": round(area, 1),
        "perimeter_m": round(perimeter, 1),
        "compactness": round(4 * math.pi * area / perimeter**2, 3) if perimeter else 0.0,
        "frontage_width_m": round(width, 1),
        "depth_m": round(depth, 1),
        "aspect": round(max(width, depth) / min(width, depth), 2) if min(width, depth) > 0 else 0.0,
        "setback_m": round(dist_m, 1),
    }


def render_text(p: dict) -> str:
    """The exact text Jev sees. Deterministic, compact, and free of ground-truth fields."""
    street, geo, osm = p["street"], p["geometry"], p["osm"]
    where = f"{osm['housenumber']} {street['name']}" if "housenumber" in osm and street.get("name") else (
        street.get("name") or "an unnamed street"
    )
    lines = [f"Building at {where}" + (" (corner of two streets)" if street.get("is_corner") else "")]
    size = f"{geo['area_m2']:.0f} m2 footprint, {geo['frontage_width_m']:.0f} m wide x {geo['depth_m']:.0f} m deep"
    if "levels" in osm:
        size += f", {osm['levels']} level{'' if osm['levels'] == 1 else 's'}"
    elif "height_m" in osm:
        size += f", ~{osm['height_m']:.0f} m tall"
    lines.append(size)
    n = geo["n_party_walls"]
    lines.append(
        "Attached to " + (f"{n} neighbour{'s' if n != 1 else ''} (shares {geo['shared_wall_ratio'] * 100:.0f}% of its walls)"
                          if n else "no neighbours (free-standing)")
    )
    tag_bits = [f"building={osm['building']}"]
    for k, v in osm.get("use_tags", {}).items():
        tag_bits.append(f"{k}={v}")
    if "name" in osm:
        tag_bits.append(f'name="{osm["name"]}"')
    if osm.get("has_unit"):
        tag_bits.append("multiple units")
    lines.append("OSM tags: " + ", ".join(tag_bits))
    if p["pois"]:
        for poi in p["pois"]:
            t = poi["tags"]
            kind = next((f"{k}={t[k]}" for k in BUSINESS_KEYS if k in t), "poi")
            extra = "".join(f", {k}={t[k]}" for k in ("cuisine", "brand") if k in t and t[k] != t.get("name"))
            nm = f' "{t["name"]}"' if "name" in t else ""
            where_ = "inside the footprint" if poi["match"] == "contained" else f"{poi['dist_m']:.0f} m away"
            lines.append(f"POI: {kind}{extra}{nm}, {where_}")
    else:
        lines.append("POIs: none within the footprint or 10 m")
    lines.append(f"Street: {street.get('name') or 'unnamed'} ({street['highway']}), {geo['setback_m']:.0f} m from the centreline")
    ctx = p["context"]
    for nb in ctx["neighbors"]:
        pos = f"{abs(nb['rel'])} {'before' if nb['rel'] < 0 else 'after'}"
        bits = [f"{nb['area_m2']:.0f} m2", "attached" if nb["attached"] else "free-standing"]
        if nb["poi_kinds"]:
            bits.append("POIs: " + ", ".join(nb["poi_kinds"]))
        if nb.get("use_tags"):
            bits.append("tags: " + ", ".join(f"{k}={v}" for k, v in nb["use_tags"].items()))
        lines.append(f"Neighbour {pos} on this side: " + "; ".join(bits))
    seg = ctx["segment"]
    lines.append(
        f"Block: {seg['n_buildings']} buildings, {seg['n_business_pois']} business POI{'' if seg['n_business_pois'] == 1 else 's'}, "
        f"{seg['frac_attached'] * 100:.0f}% attached"
    )
    return "\n".join(lines)
