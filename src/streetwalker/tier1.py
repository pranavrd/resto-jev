"""Tier 1 of the cascade: caption a street image of the building, then ask Jev again with the caption (decision 0018).

For every building in the escalation band: a panorama crop aimed at the building when a panorama pick exists
(the best-known setup, decision 0014), otherwise the lower part of the picked ordinary photo (decision 0012).
Results go to `tier1_result`, so a run can be stopped and resumed.   Usage: .venv/bin/python -u -m streetwalker.tier1 [--tau 0.77]
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from streetwalker import db
from streetwalker.cascade import load_rows
from streetwalker.imagery import fov_for_frontage
from streetwalker.images_cache import fetch
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import build_tier1_questions
from streetwalker.pano import level_roll, perspective_view
from streetwalker.vlm import CAPTION_PROMPTS, caption, load_vlm, parse_caption, parse_caption_v4

CROPS = db.ROOT / "data" / "images" / "crops"
LOWER_KEEP = 0.55  # windshield cameras tilt up, so ground floors sit in the lower part of the photo


def make_crop(building_id: int, image_id: str, heading: float, bearing: float, fov: float) -> tuple[str, float]:
    """A levelled perspective view of a panorama toward the building. Cached next to its roll angle."""
    CROPS.mkdir(parents=True, exist_ok=True)
    out = CROPS / f"b{building_id}_{image_id}_fov{round(fov)}.jpg"
    meta = out.with_suffix(".roll")
    if out.exists() and meta.exists():
        return str(out), float(meta.read_text())
    pano = np.asarray(Image.open(fetch(image_id, "original")).convert("RGB"))
    roll = level_roll(pano, heading, bearing, fov_deg=fov)
    Image.fromarray(perspective_view(pano, heading, bearing, fov_deg=fov, roll_deg=roll)).save(out, quality=92)
    meta.write_text(str(roll))
    return str(out), roll


def crop_lower(path: str, keep: float = LOWER_KEEP) -> str:
    out = Path(path).with_name(Path(path).stem + f"_lower{int(keep * 100)}.jpg")
    if not out.exists():
        im = Image.open(path)
        w, h = im.size
        im.crop((0, int(h * (1 - keep)), w, h)).save(out, quality=92)
    return str(out)


def pano_state(text: str, cap_text: str) -> tuple[str, dict]:
    p = parse_caption_v4(cap_text)
    state = (
        text + "\nStreet photo (2026, cut from a panorama aimed at the target building), described by a vision model. "
        f"Street level: {p.street_level}. Sign on the target building: {p.center_sign or 'none'}. "
        f"Signs on neighbouring buildings (not the target): {p.neighbour_signs or 'none'}."
    )
    return state, {"street_level": p.street_level, "own_sign": p.center_sign}


def photo_state(text: str, cap_text: str, year: int | None) -> tuple[str, dict]:
    p = parse_caption(cap_text)
    state = text + f"\nStreet photo ({year}, may show a neighbouring building or be out of date), described by a vision model: " + cap_text
    return state, {"street_level": p.street_level, "own_sign": p.sign}


def band_ids(conn, tau: float) -> list[int]:
    return [r.building_id for r in load_rows(conn, ("train", "dev", "test")) if r.conf < tau]


def run(conn, tau: float) -> None:
    ids = band_ids(conn, tau)
    done = {r[0] for r in conn.execute("SELECT building_id FROM tier1_result WHERE error IS NULL")}
    todo = [b for b in ids if b not in done]
    rows = conn.execute(
        """
        SELECT b.id, e.text, pp.image_id, pp.heading_deg, pp.bearing_deg, pp.dist_m,
               (e.payload->'geometry'->>'frontage_width_m')::float, ip.image_id, ip.year
        FROM building b JOIN evidence e ON e.building_id = b.id AND e.tier = 0
        LEFT JOIN pano_pick pp ON pp.building_id = b.id LEFT JOIN image_pick ip ON ip.building_id = b.id
        WHERE b.id = ANY(%s) AND (pp.building_id IS NOT NULL OR ip.building_id IS NOT NULL) ORDER BY b.id
        """,
        (todo,),
    ).fetchall()
    print(f"band {len(ids)} buildings (conf < {tau}); {len(done)} done, {len(rows)} to run (the rest have no image)", flush=True)
    vlm, client, questions = load_vlm(), make_client(), build_tier1_questions("p1")
    t0 = time.perf_counter()
    for i, (bid, text, pano_id, heading, bearing, dist, width, photo_id, year) in enumerate(rows, 1):
        source, image_id, cap, state, parsed, vlm_s, err = ("pano-tight-v4" if pano_id else "photo-lower55-v3"), pano_id or photo_id, None, None, {}, None, None
        try:
            if pano_id:
                path, _roll = make_crop(bid, pano_id, heading, bearing, fov_for_frontage(width, dist))
                cap = caption(vlm, path, CAPTION_PROMPTS["v4"])
                state, parsed = pano_state(text, cap.text)
            else:
                cap = caption(vlm, crop_lower(fetch(photo_id, 1024)), CAPTION_PROMPTS["v3"])
                state, parsed = photo_state(text, cap.text, year)
            vlm_s = cap.seconds
        except OSError as e:  # a deleted or unreachable image
            err = f"{type(e).__name__}: {e}"[:300]
        d1 = d3 = d5 = jev_ms = None
        if state:
            res = ask(client, state, questions)
            if res.error:
                err = res.error
            else:
                a = {x.question: x for x in res.answers}
                d1, d3, d5, jev_ms = a["d1"].probs, a["d3"].probs["yes"], a["d5"].probs["yes"], res.latency_ms
        conn.execute(
            """
            INSERT INTO tier1_result (building_id, source, image_id, caption, street_level, own_sign, d1, d3_yes, d5_yes, vlm_seconds, jev_ms, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            ON CONFLICT (building_id) DO UPDATE SET source = EXCLUDED.source, image_id = EXCLUDED.image_id, caption = EXCLUDED.caption,
              street_level = EXCLUDED.street_level, own_sign = EXCLUDED.own_sign, d1 = EXCLUDED.d1, d3_yes = EXCLUDED.d3_yes,
              d5_yes = EXCLUDED.d5_yes, vlm_seconds = EXCLUDED.vlm_seconds, jev_ms = EXCLUDED.jev_ms, error = EXCLUDED.error, created_at = now()
            """,
            (bid, source, image_id, cap.text if cap else None, parsed.get("street_level"), parsed.get("own_sign"),
             json.dumps(d1) if d1 else None, d3, d5, vlm_s, jev_ms, err),
        )
        conn.commit()
        if i % 10 == 0 or err:
            print(f"  {i}/{len(rows)} ({(time.perf_counter() - t0) / 60:.1f} min){'  ERROR ' + err if err else ''}", flush=True)
    print(f"done in {(time.perf_counter() - t0) / 60:.1f} min", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau", type=float, default=0.77, help="escalate buildings whose Tier 0 confidence is below this")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        run(conn, args.tau)


if __name__ == "__main__":
    main()
