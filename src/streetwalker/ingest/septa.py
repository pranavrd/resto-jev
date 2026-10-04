"""SEPTA GTFS ingest (decision 0017): stops near the survey areas with their service on one typical weekday.

The public feed is a single release asset holding a bus feed (which also carries the subway and trolley lines) and a
rail feed. The release tag is pinned so a re-run reproduces the same service; bump it deliberately.
"""

import json
import urllib.request
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg

from streetwalker import db
from streetwalker.areas import AREAS
from streetwalker.transit import feed_dates, load_stops, typical_weekday

RELEASE = "v202609270"
URL = f"https://github.com/septadev/GTFS/releases/download/{RELEASE}/gtfs_public.zip"
DATA = db.ROOT / "data" / "septa"
FEEDS = {"bus": "google_bus", "rail": "google_rail"}
MARGIN_DEG = 0.03  # keep stops this far (about 2.5 to 3.3 km) outside each area box


def download() -> Path:
    """Fetch and unpack the feed unless it is already on disk."""
    DATA.mkdir(parents=True, exist_ok=True)
    archive = DATA / "gtfs_public.zip"
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=300) as resp, archive.open("wb") as f:
            f.write(resp.read())
    for name in FEEDS.values():
        if not (DATA / name / "stops.txt").exists():
            inner = DATA / f"{name}.zip"
            if not inner.exists():
                with zipfile.ZipFile(archive) as z:
                    z.extract(f"{name}.zip", DATA)
            with zipfile.ZipFile(inner) as z:
                z.extractall(DATA / name)
    return DATA


def survey_bounds() -> tuple[float, float, float, float]:
    xs1, ys1, xs2, ys2 = zip(*(a.bbox for a in AREAS), strict=True)
    return min(xs1) - MARGIN_DEG, min(ys1) - MARGIN_DEG, max(xs2) + MARGIN_DEG, max(ys2) + MARGIN_DEG


def ingest_septa(conn: psycopg.Connection, today: date | None = None) -> int:
    root = download()
    spans = {feed: feed_dates(root / folder) for feed, folder in FEEDS.items()}
    day = typical_weekday([s for s, _, _ in spans.values()], [e for _, e, _ in spans.values()], today or datetime.now(UTC).date())
    conn.execute("DELETE FROM transit_stop")
    n = 0
    for feed, folder in FEEDS.items():
        for s in load_stops(root / folder, day, survey_bounds()):
            conn.execute(
                "INSERT INTO transit_stop (feed, stop_id, name, geom, modes, service, weekday_trips, service_date, feed_version) "
                "VALUES (%s, %s, %s, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 32618), 4326), %s, %s, %s, %s, %s)",
                (feed, s.stop_id, s.name, s.x, s.y, sorted(s.modes),
                 json.dumps({f"{r}|{d}": c for (r, d), c in s.service.items()}), s.trips, day, spans[feed][2]),
            )
            n += 1
    return n
