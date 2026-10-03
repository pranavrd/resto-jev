"""Crosswalk from City land use / OPA codes to the project's D1 classes, plus the train/dev/test split.

The crosswalk is a modelling choice, not a fact; it is documented in decision 0007. Ground truth is
used to score classifiers and must never feed the evidence bundles.
"""

CROSSWALK_VERSION = "v1"

D1_CLASSES = (
    "residential", "commercial", "mixed-use", "industrial", "civic-institutional", "vacant", "other",
)

# PCPC land use, second digit group (c_dig2) -> class
LAND_USE_C2 = {
    11: "residential", 12: "residential", 13: "residential",  # low / medium / high density
    21: "commercial",  # commercial consumer (stores, restaurants, auto)
    22: "commercial",  # commercial business / professional (offices, services)
    23: "mixed-use",   # commercial mixed residential (store or office with residential)
    31: "industrial",
    41: "civic-institutional",
    61: "civic-institutional",  # culture / amusement
    62: "civic-institutional",  # active recreation
    91: "vacant",
    51: "other", 52: "other", 71: "other", 72: "other", 81: "other", 92: "other",
}
# Fallback when only the first digit is known
LAND_USE_C1 = {
    1: "residential", 2: "commercial", 3: "industrial", 4: "civic-institutional", 5: "other",
    6: "civic-institutional", 7: "other", 8: "other", 9: "vacant",
}

OPA_CLASS = {
    "SINGLE FAMILY": "residential", "MULTI FAMILY": "residential", "APARTMENTS  > 4 UNITS": "residential",
    "MIXED USE": "mixed-use",
    "COMMERCIAL": "commercial", "OFFICES": "commercial", "RETAIL": "commercial", "HOTEL": "commercial",
    "INDUSTRIAL": "industrial",
    "SPECIAL PURPOSE": "civic-institutional",
    "VACANT LAND": "vacant", "VACANT LAND - RESIDENTIAL": "vacant", "VACANT LAND - NON-RESIDENTIAL": "vacant",
    "GARAGE - RESIDENTIAL": "other", "GARAGE - COMMERCIAL": "other",
}


def land_use_class(c1: int | None, c2: int | None) -> str:
    if c2 in LAND_USE_C2:
        return LAND_USE_C2[c2]
    return LAND_USE_C1.get(c1, "other")


def opa_class(category: str | None) -> str | None:
    return OPA_CLASS.get(category) if category else None


def label_status(land_use: str, opa: str | None) -> str:
    """agree: OPA says the same class; land_use_only: no OPA parcel point in the footprint;
    disputed: OPA says something else (OPA is known to code tax-exempt churches and schools as commercial)."""
    if opa is None:
        return "land_use_only"
    return "agree" if opa == land_use else "disputed"


SPLIT_SHARES = {"train": 0.6, "dev": 0.2, "test": 0.2}


def assign_splits(
    groups: dict[str, tuple[str, float]], fixed: dict[str, str] | None = None
) -> dict[str, str]:
    """Assign street groups to train/dev/test, balancing weight within each area.

    groups maps group key -> (area, weight). Groups already in `fixed` keep their split (frozen), and
    count towards the balance. Largest groups are placed first, each into the split furthest below its
    target share. Deterministic: ties break on the group key.
    """
    fixed = dict(fixed or {})
    out = dict(fixed)
    fill: dict[str, dict[str, float]] = {}
    for key, (area, w) in groups.items():
        if key in fixed:
            fill.setdefault(area, dict.fromkeys(SPLIT_SHARES, 0.0))[fixed[key]] += w
    for key, (area, w) in sorted(groups.items(), key=lambda kv: (-kv[1][1], kv[0])):
        if key in fixed:
            continue
        f = fill.setdefault(area, dict.fromkeys(SPLIT_SHARES, 0.0))
        pick = min(SPLIT_SHARES, key=lambda s: ((f[s] + w) / SPLIT_SHARES[s], s))
        f[pick] += w
        out[key] = pick
    return out
