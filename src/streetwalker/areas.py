"""Survey areas (decision 0003). Boxes are rough; refine to street-aligned polygons after ingest."""

from dataclasses import dataclass

from shapely.geometry import Polygon, box


@dataclass(frozen=True)
class Area:
    slug: str
    name: str
    profile: str
    bbox: tuple[float, float, float, float]  # lng_min, lat_min, lng_max, lat_max

    @property
    def polygon(self) -> Polygon:
        return box(*self.bbox)


AREAS = [
    Area("rittenhouse", "Rittenhouse", "dense commercial core", (-75.1745, 39.9475, -75.1685, 39.9520)),
    Area("east_passyunk", "East Passyunk", "mixed rowhouse corridor", (-75.1710, 39.9235, -75.1630, 39.9295)),
    Area("roxborough", "Roxborough", "low-density residential", (-75.2195, 40.0345, -75.2115, 40.0405)),
]
