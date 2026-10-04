"""Download Mapillary photos into a local cache (data/images, gitignored; never committed or redistributed).

Photos are CC BY-SA 4.0 and are only used locally to produce captions. The database keeps image ids and
captions, not pictures (decision 0002).
"""

import json
import os
import urllib.parse
import urllib.request

from dotenv import load_dotenv

from streetwalker.db import ROOT

CACHE = ROOT / "data" / "images"
GRAPH = "https://graph.mapillary.com"


def _token() -> str:
    load_dotenv(ROOT / ".env")
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        raise SystemExit("MAPILLARY_TOKEN is not set in .env")
    return token


def fetch(image_id: str, size: int | str = 1024) -> str:
    """Return the local path of the image, downloading it if needed. size is 256, 1024, 2048 or "original"."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{image_id}_{size}.jpg"
    if path.exists():
        return str(path)
    meta_url = f"{GRAPH}/{image_id}?{urllib.parse.urlencode({'fields': f'thumb_{size}_url'})}"
    req = urllib.request.Request(meta_url, headers={"Authorization": f"OAuth {_token()}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        url = json.load(resp)[f"thumb_{size}_url"]
    with urllib.request.urlopen(url, timeout=60) as resp:  # a signed CDN url; no token needed or sent
        path.write_bytes(resp.read())
    return str(path)
