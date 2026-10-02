"""Week 1 check: Mapillary street-level image coverage for candidate survey areas.

Needs a free Mapillary developer client token in the MAPILLARY_TOKEN env var (or in .env).
Stdlib only. Run: python3 scripts/week1_mapillary_coverage.py

Reports, per area: image count, capture-year histogram, share of panoramas, and the share of
~30 m grid cells containing at least one image (a rough proxy for "can we find a frontage photo").
"""

import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from week1_area_density import CANDIDATES

GRAPH = "https://graph.mapillary.com/images"
LIMIT = 2000  # API page cap; a response at the cap means the tile may be truncated, so split it
CELL_DEG = 0.0003  # ~33 m of latitude


def load_token() -> str:
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        env = Path(__file__).resolve().parent.parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("MAPILLARY_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    if not token:
        raise SystemExit("Set MAPILLARY_TOKEN (env var or .env). Create a free token at mapillary.com/developer.")
    return token


def fetch(bbox: tuple[float, float, float, float], token: str) -> list[dict]:
    x1, y1, x2, y2 = bbox
    params = {
        "fields": "id,captured_at,compass_angle,is_pano,geometry",
        "bbox": f"{x1},{y1},{x2},{y2}",
        "limit": LIMIT,
    }
    req = urllib.request.Request(
        f"{GRAPH}?{urllib.parse.urlencode(params)}", headers={"Authorization": f"OAuth {token}"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)["data"]
    if len(data) < LIMIT:
        return data
    xm, ym = (x1 + x2) / 2, (y1 + y2) / 2  # truncated: split into quadrants and recurse
    quads = [(x1, y1, xm, ym), (xm, y1, x2, ym), (x1, ym, xm, y2), (xm, ym, x2, y2)]
    seen: dict[str, dict] = {}
    for q in quads:
        for img in fetch(q, token):
            seen[img["id"]] = img
    return list(seen.values())


def main() -> None:
    token = load_token()
    for name, bbox in CANDIDATES.items():
        x1, y1, x2, y2 = bbox
        images = fetch(bbox, token)
        years = Counter(
            datetime.fromtimestamp(i["captured_at"] / 1000, UTC).year
            for i in images
            if i.get("captured_at")
        )
        cells = {
            (int((i["geometry"]["coordinates"][0] - x1) / CELL_DEG),
             int((i["geometry"]["coordinates"][1] - y1) / CELL_DEG))
            for i in images
        }
        total_cells = int((x2 - x1) / CELL_DEG + 1) * int((y2 - y1) / CELL_DEG + 1)
        panos = sum(1 for i in images if i.get("is_pano"))
        print(f"\n=== {name}  bbox={bbox}")
        print(f"images: {len(images)}  panoramas: {panos}")
        print("by year:", dict(sorted(years.items())))
        print(f"grid cells with an image: {len(cells)}/{total_cells} ({len(cells) / total_cells:.0%})")


if __name__ == "__main__":
    main()
