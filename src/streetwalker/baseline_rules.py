"""Rule-based baselines: classify a building from its tier-0 evidence bundle with ordered rules.

Three rule sets form the first rungs of the evidence ablation (decision 0007):
  rules-v1  tags only (OSM tags and POIs)            frozen as first written, before seeing any results
  rules-v2  + footprint geometry                     developed against the train split, checked on dev
  rules-v3  + street context (road class, block POIs)  same
They use the same evidence Jev sees, nothing more, so they are a fair bar for Jev to beat. Rules are
ordered; the first match wins and its name is recorded for error analysis.
"""

from dataclasses import dataclass

RULES_VERSION = "rules-v1"  # the tags-only baseline; v2 and v3 are in RULESETS

FOOD_AMENITY = {"restaurant", "fast_food", "food_court", "cafe", "bar", "pub", "biergarten", "ice_cream"}
FOOD_SHOP = {"bakery", "coffee", "pastry", "deli", "ice_cream", "chocolate", "tea", "confectionery"}
GROCERY_SHOP = {"supermarket", "convenience", "greengrocer", "grocery", "butcher", "seafood", "alcohol", "wine"}
PERSONAL_SHOP = {"hairdresser", "beauty", "cosmetics", "laundry", "dry_cleaning", "tailor", "massage", "tattoo", "nail_salon"}
PERSONAL_AMENITY = {"bank", "pharmacy", "dentist", "doctors", "clinic", "veterinary", "post_office", "spa"}
CIVIC_AMENITY = {
    "school", "college", "university", "kindergarten", "place_of_worship", "library", "hospital", "townhall",
    "community_centre", "fire_station", "police", "courthouse", "social_facility", "theatre", "arts_centre",
}
CIVIC_BUILDING = {
    "church", "chapel", "synagogue", "mosque", "temple", "cathedral", "school", "university", "college", "hospital",
    "public", "civic", "government", "kindergarten", "fire_station", "sports_centre", "stadium", "religious", "monastery",
}
INDUSTRIAL_BUILDING = {"industrial", "warehouse", "factory", "manufacture"}
ACCESSORY_BUILDING = {"garage", "garages", "carport", "shed", "hut", "roof", "greenhouse", "outbuilding", "barn"}
RESIDENTIAL_BUILDING = {
    "house", "detached", "semidetached_house", "terrace", "residential", "apartments", "dormitory", "bungalow",
    "duplex", "townhouse", "rowhouse",
}
COMMERCIAL_BUILDING = {"retail", "commercial", "office", "supermarket", "kiosk", "hotel", "mall"}

HOUSE_BUILDING = {"house", "detached", "semidetached_house", "terrace", "townhouse", "rowhouse", "duplex", "bungalow"}
CORRIDOR_ROADS = {"primary", "tertiary"}  # v3: in these areas, silent buildings on these streets are mostly commercial

ROWHOUSE_MAX_AREA_M2 = 300  # an attached footprint this small, on a narrow lot, reads as a rowhouse
ROWHOUSE_MAX_WIDTH_M = 10


@dataclass(frozen=True)
class Prediction:
    d1: str
    d2: str | None
    d3_food: bool
    rule: str


def _tag_dicts(payload: dict) -> list[dict]:
    """Every tag dictionary that describes a business at this building: its own use tags and its POIs."""
    tags = [dict(payload["osm"].get("use_tags", {}))]
    tags += [p["tags"] for p in payload["pois"]]
    return [t for t in tags if t]


def _has_business(tag_dicts: list[dict]) -> bool:
    for t in tag_dicts:
        if any(k in t for k in ("shop", "office", "craft", "healthcare")):
            return True
        if t.get("amenity") not in (None, "parking") and t["amenity"] not in CIVIC_AMENITY:
            return True
        if t.get("tourism") not in (None, "museum"):
            return True
        if "leisure" in t:
            return True
    return False


def _is_civic(tag_dicts: list[dict], building: str, osm: dict) -> bool:
    if building in CIVIC_BUILDING or "religion" in osm.get("use_tags", {}):
        return True
    return any(t.get("amenity") in CIVIC_AMENITY or t.get("tourism") == "museum" for t in tag_dicts)


def commercial_type(tag_dicts: list[dict]) -> str:
    """D2 by priority: restaurant, cafe, bar, grocery, retail, personal services, office, other."""
    amen = {t["amenity"] for t in tag_dicts if "amenity" in t}
    shop = {t["shop"] for t in tag_dicts if "shop" in t}
    if amen & {"restaurant", "fast_food", "food_court"}:
        return "restaurant"
    if "cafe" in amen or shop & {"coffee", "tea", "ice_cream"} or "ice_cream" in amen:
        return "cafe"
    if amen & {"bar", "pub", "biergarten", "nightclub"}:
        return "bar"
    if shop & GROCERY_SHOP:
        return "grocery"
    if shop - PERSONAL_SHOP - {"vacant"}:
        return "retail"
    if shop & PERSONAL_SHOP or amen & PERSONAL_AMENITY or any("healthcare" in t for t in tag_dicts):
        return "personal services"
    if any("office" in t for t in tag_dicts) or "coworking_space" in amen:
        return "office"
    return "retail" if shop else "other"


def is_food(tag_dicts: list[dict]) -> bool:
    return any(t.get("amenity") in FOOD_AMENITY or t.get("shop") in FOOD_SHOP for t in tag_dicts)


def predict(payload: dict) -> Prediction:
    osm, geo = payload["osm"], payload["geometry"]
    building = osm.get("building", "yes")
    tags = _tag_dicts(payload)
    food = is_food(tags)
    business = _has_business(tags)

    if _is_civic(tags, building, osm):
        return Prediction("civic-institutional", None, food, "civic_tag")
    if building in INDUSTRIAL_BUILDING:
        return Prediction("industrial", None, food, "industrial_tag")
    if building == "parking" or any(t.get("amenity") == "parking" for t in tags):
        return Prediction("other", None, food, "parking_tag")
    if business:
        d2 = commercial_type(tags)
        if building in RESIDENTIAL_BUILDING or osm.get("has_unit"):
            return Prediction("mixed-use", d2, food, "business_in_residential_building")
        if building in COMMERCIAL_BUILDING:
            return Prediction("commercial", d2, food, "business_in_commercial_building")
        rowhouse_like = (
            geo["n_party_walls"] >= 1 and geo["area_m2"] <= ROWHOUSE_MAX_AREA_M2
            and geo["frontage_width_m"] <= ROWHOUSE_MAX_WIDTH_M
        )
        if rowhouse_like:
            return Prediction("mixed-use", d2, food, "business_in_rowhouse_footprint")
        return Prediction("commercial", d2, food, "business_in_other_footprint")
    if building in COMMERCIAL_BUILDING:
        return Prediction("commercial", "retail" if building == "retail" else "other", food, "commercial_tag")
    if building in ACCESSORY_BUILDING:
        return Prediction("residential", None, food, "accessory_tag")
    if building in RESIDENTIAL_BUILDING:
        return Prediction("residential", None, food, "residential_tag")
    return Prediction("residential", None, food, "default_residential")


def _rowhouse_like(geo: dict) -> bool:
    return (
        geo["n_party_walls"] >= 1 and geo["area_m2"] <= ROWHOUSE_MAX_AREA_M2
        and geo["frontage_width_m"] <= ROWHOUSE_MAX_WIDTH_M
    )


def predict_v1(payload: dict) -> Prediction:
    return predict(payload)


def _predict_geometry(payload: dict, corridor: bool) -> Prediction:
    """v2 (corridor=False) and v3 (corridor=True). Same civic, industrial and parking rules as v1; the
    business and commercial-tag rules decide mixed-use versus commercial by footprint shape, because
    train showed `addr:unit` and apartment tags mark big multi-tenant buildings, not residential ones."""
    osm, geo = payload["osm"], payload["geometry"]
    building = osm.get("building", "yes")
    tags = _tag_dicts(payload)
    food = is_food(tags)
    rowhouse = _rowhouse_like(geo)

    if _is_civic(tags, building, osm):
        return Prediction("civic-institutional", None, food, "civic_tag")
    if building in INDUSTRIAL_BUILDING:
        return Prediction("industrial", None, food, "industrial_tag")
    if building == "parking" or any(t.get("amenity") == "parking" for t in tags):
        return Prediction("other", None, food, "parking_tag")
    if _has_business(tags):
        d2 = commercial_type(tags)
        if building in HOUSE_BUILDING:
            return Prediction("mixed-use", d2, food, "business_in_house_tag")
        if rowhouse:
            return Prediction("mixed-use", d2, food, "business_in_rowhouse_footprint")
        return Prediction("commercial", d2, food, "business_in_larger_footprint")
    if building in COMMERCIAL_BUILDING:
        d2 = "retail" if building == "retail" else "other"
        if rowhouse:
            return Prediction("mixed-use", d2, food, "commercial_tag_rowhouse_footprint")
        return Prediction("commercial", d2, food, "commercial_tag")
    if building in ACCESSORY_BUILDING:
        return Prediction("residential", None, food, "accessory_tag")
    if building in RESIDENTIAL_BUILDING:
        return Prediction("residential", None, food, "residential_tag")
    if (
        corridor and building == "yes" and geo["n_party_walls"] >= 1
        and payload["street"]["highway"] in CORRIDOR_ROADS
        and payload["context"]["segment"]["n_business_pois"] >= 1  # the block already has known businesses
    ):
        if rowhouse:
            return Prediction("mixed-use", None, food, "corridor_silent_rowhouse")
        return Prediction("commercial", None, food, "corridor_silent_building")
    return Prediction("residential", None, food, "default_residential")


def predict_v2(payload: dict) -> Prediction:
    return _predict_geometry(payload, corridor=False)


def predict_v3(payload: dict) -> Prediction:
    return _predict_geometry(payload, corridor=True)


RULESETS = {"rules-v1": predict_v1, "rules-v2": predict_v2, "rules-v3": predict_v3}
