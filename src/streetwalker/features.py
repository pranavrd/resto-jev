"""Numeric features for the learned baselines, extracted from a tier-0 evidence bundle.

Same evidence Jev sees, nothing more. Street names and ids are deliberately excluded: the split keeps
blocks together but not whole streets, so a street-name feature would leak across splits. Neither
the area nor the encounter order is a feature.
"""

import math

from streetwalker.baseline_rules import (
    ACCESSORY_BUILDING,
    CIVIC_BUILDING,
    COMMERCIAL_BUILDING,
    HOUSE_BUILDING,
    INDUSTRIAL_BUILDING,
    RESIDENTIAL_BUILDING,
    _has_business,
    _is_civic,
    _tag_dicts,
    is_food,
)

NAN = math.nan
ROADS = ("residential", "service", "tertiary", "secondary", "primary")

GEOMETRY = [
    "area_m2", "perimeter_m", "compactness", "frontage_width_m", "depth_m", "aspect", "setback_m",
    "n_party_walls", "shared_wall_ratio", "levels", "height_m",
]
TAGS = [
    "building_cat", "has_unit", "has_name", "has_use_tag", "n_pois", "n_pois_contained", "n_pois_nearby",
    "has_business", "has_food", "has_retail", "has_office", "has_service", "has_civic",
]
CONTEXT = [
    "road_class", "is_corner", "seg_n_business_pois", "seg_poi_density", "seg_frac_attached",
    "nb_n", "nb_n_with_pois", "nb_n_attached", "nb_n_with_use_tags", "nb_mean_area_m2", "nb_nearest_poi_rel",
]
FEATURE_SETS = {
    "geometry": GEOMETRY,
    "tags": GEOMETRY + TAGS,
    "full": GEOMETRY + TAGS + CONTEXT,
}
CATEGORICAL = {"building_cat", "road_class"}


def building_category(btag: str) -> str:
    if btag in HOUSE_BUILDING:
        return "house"
    if btag == "apartments":
        return "apartments"
    if btag in RESIDENTIAL_BUILDING:
        return "residential_other"
    if btag in COMMERCIAL_BUILDING:
        return "commercial"
    if btag in CIVIC_BUILDING:
        return "civic"
    if btag in INDUSTRIAL_BUILDING:
        return "industrial"
    if btag in ACCESSORY_BUILDING or btag == "parking":
        return "accessory"
    return "yes" if btag == "yes" else "other"


def extract(payload: dict) -> dict:
    osm, geo, street, ctx = payload["osm"], payload["geometry"], payload["street"], payload["context"]
    tags = _tag_dicts(payload)
    shops = {t["shop"] for t in tags if "shop" in t}
    f: dict = {k: geo[k] for k in (
        "area_m2", "perimeter_m", "compactness", "frontage_width_m", "depth_m", "aspect", "setback_m",
        "n_party_walls", "shared_wall_ratio",
    )}
    f["levels"] = osm.get("levels", NAN)
    f["height_m"] = osm.get("height_m", NAN)

    pois = payload["pois"]
    f.update({
        "building_cat": building_category(osm.get("building", "yes")),
        "has_unit": int(bool(osm.get("has_unit"))),
        "has_name": int("name" in osm),
        "has_use_tag": int("use_tags" in osm),
        "n_pois": len(pois),
        "n_pois_contained": sum(p["match"] == "contained" for p in pois),
        "n_pois_nearby": sum(p["match"] != "contained" for p in pois),
        "has_business": int(_has_business(tags)),
        "has_food": int(is_food(tags)),
        "has_retail": int(bool(shops)),
        "has_office": int(any("office" in t for t in tags)),
        "has_service": int(any("healthcare" in t or t.get("amenity") in {"bank", "pharmacy"} for t in tags)),
        "has_civic": int(_is_civic(tags, osm.get("building", "yes"), osm)),
    })

    nbs = ctx["neighbors"]
    seg = ctx["segment"]
    nearest = [abs(n["rel"]) for n in nbs if n["poi_kinds"]]
    f.update({
        "road_class": street["highway"] if street["highway"] in ROADS else "other",
        "is_corner": int(bool(street.get("is_corner"))),
        # seg_n_buildings is deliberately not a feature: constant within a segment and nearly unique to it,
        # it lets trees memorise a segment's class mix instead of generalising (seen in grouped CV)
        "seg_n_business_pois": seg["n_business_pois"],
        "seg_poi_density": seg["n_business_pois"] / seg["n_buildings"],
        "seg_frac_attached": seg["frac_attached"],
        "nb_n": len(nbs),
        "nb_n_with_pois": sum(bool(n["poi_kinds"]) for n in nbs),
        "nb_n_attached": sum(bool(n["attached"]) for n in nbs),
        "nb_n_with_use_tags": sum(bool(n["use_tags"]) for n in nbs),
        "nb_mean_area_m2": sum(n["area_m2"] for n in nbs) / len(nbs) if nbs else NAN,
        "nb_nearest_poi_rel": min(nearest) if nearest else 3,  # 3 = none within the two nearest on this side
    })
    return f
