"""Tier 1 image selection: pick the street-level photo whose camera is looking at a building's frontage.

Pure geometry. A Mapillary image has a position and a compass heading (degrees clockwise from north). It
shows a building if the building's frontage point is roughly in the direction the camera faces and neither
too close nor too far. Panoramas are skipped: their heading is not a viewing direction.
"""

import math
from dataclasses import dataclass

MIN_DIST_M = 4.0
MAX_DIST_M = 35.0
MAX_ANGLE_DEG = 40.0  # frontage must be this close to the centre of the camera's view
IDEAL_DIST_M = 12.0
AGE_PENALTY_PER_YEAR = 0.02  # prefer newer imagery when two photos are otherwise equal


@dataclass(frozen=True)
class Image:
    id: str
    lng: float
    lat: float
    compass: float | None
    is_pano: bool
    year: int | None


@dataclass(frozen=True)
class Pick:
    image: Image
    dist_m: float
    angle_deg: float  # between where the camera faces and the direction of the frontage
    score: float  # lower is better


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dy = (lat2 - lat1) * 111_320
    dx = (lng2 - lng1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Direction from point 1 to point 2, degrees clockwise from north, in [0, 360)."""
    dy = lat2 - lat1
    dx = (lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.degrees(math.atan2(dx, dy)) % 360


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two headings, in [0, 180]."""
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def pick_image(
    frontage_lng: float, frontage_lat: float, images: list[Image], this_year: int = 2026
) -> Pick | None:
    best: Pick | None = None
    for im in images:
        if im.is_pano or im.compass is None:
            continue
        d = distance_m(im.lat, im.lng, frontage_lat, frontage_lng)
        if not MIN_DIST_M <= d <= MAX_DIST_M:
            continue
        ang = angle_diff(im.compass, bearing_deg(im.lat, im.lng, frontage_lat, frontage_lng))
        if ang > MAX_ANGLE_DEG:
            continue
        age = (this_year - im.year) if im.year else 10
        score = ang / MAX_ANGLE_DEG + abs(d - IDEAL_DIST_M) / MAX_DIST_M + AGE_PENALTY_PER_YEAR * age
        if best is None or (score, im.id) < (best.score, best.image.id):
            best = Pick(im, d, ang, score)
    return best


MAX_PANO_DIST_M = 30.0  # a panorama covers 360 degrees, so only distance matters; farther than this signs are unreadable


@dataclass(frozen=True)
class PanoPick:
    image: Image
    dist_m: float
    bearing_deg: float  # compass direction from the camera to the frontage: where to point the crop
    score: float


def pick_panorama(
    frontage_lng: float, frontage_lat: float, images: list[Image], this_year: int = 2026
) -> PanoPick | None:
    """Closest-to-ideal-distance panorama (4 to 30 m), newest wins ties. Direction is free: the view is cut toward the frontage."""
    best: PanoPick | None = None
    for im in images:
        if not im.is_pano:
            continue
        d = distance_m(im.lat, im.lng, frontage_lat, frontage_lng)
        if not MIN_DIST_M <= d <= MAX_PANO_DIST_M:
            continue
        age = (this_year - im.year) if im.year else 10
        score = abs(d - IDEAL_DIST_M) / MAX_PANO_DIST_M + AGE_PENALTY_PER_YEAR * age
        if best is None or (score, im.id) < (best.score, best.image.id):
            best = PanoPick(im, d, bearing_deg(im.lat, im.lng, frontage_lat, frontage_lng), score)
    return best


MIN_FOV_DEG = 35.0
MAX_FOV_DEG = 75.0
FRAME_FILL = 1.6  # the view spans this many frontage widths, so the target fills about 60% of the frame


def fov_for_frontage(frontage_width_m: float, dist_m: float) -> float:
    """Horizontal field of view (degrees) that frames a building of this width at this distance, with some context."""
    half = math.atan((frontage_width_m * FRAME_FILL / 2) / max(dist_m, 1.0))
    return min(MAX_FOV_DEG, max(MIN_FOV_DEG, math.degrees(2 * half)))
