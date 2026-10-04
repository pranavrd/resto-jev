"""Pilot: panorama crops for East Passyunk. Cut a leveled view toward each building, caption it, ask Jev with the caption.

Variants:
  wide-v3    fixed 80 degree field of view, caption prompt v3 (the first pilot, decision 0013)
  tight-v3   field of view from the building's frontage width and distance, caption prompt v3
  tight-v4   tight view and a caption that separates the target's own sign from neighbours' signs
Each Jev call also asks D5: does the description report something on the target building itself?

Needs the panoramas in the local cache and image picks. Run: .venv/bin/python -u scripts/pano_pilot.py tight-v3 tight-v4
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from streetwalker import db
from streetwalker.imagery import fov_for_frontage
from streetwalker.images_cache import fetch
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import build_tier1_questions
from streetwalker.pano import level_roll, perspective_view
from streetwalker.vlm import CAPTION_PROMPTS, caption, load_vlm, parse_caption, parse_caption_v4

CROPS = Path("data/images/crops")
VARIANTS = {"wide-v3": (False, "v3"), "tight-v3": (True, "v3"), "tight-v4": (True, "v4")}


def make_crop(building_id: int, image_id: str, heading: float, bearing: float, fov: float) -> tuple[str, float]:
    out = CROPS / f"b{building_id}_{image_id}_fov{round(fov)}.jpg"
    meta = out.with_suffix(".roll")
    if out.exists() and meta.exists():
        return str(out), float(meta.read_text())
    pano = np.asarray(Image.open(fetch(image_id, "original")).convert("RGB"))
    roll = level_roll(pano, heading, bearing, fov_deg=fov)
    Image.fromarray(perspective_view(pano, heading, bearing, fov_deg=fov, roll_deg=roll)).save(out, quality=92)
    meta.write_text(str(roll))
    return str(out), roll


def tier1_state(text: str, cap_text: str, prompt: str) -> tuple[str, dict]:
    if prompt == "v4":
        p = parse_caption_v4(cap_text)
        state = (
            text + "\nStreet photo (2026, cut from a panorama aimed at the target building), described by a vision model. "
            f"Street level: {p.street_level}. Sign on the target building: {p.center_sign or 'none'}. "
            f"Signs on neighbouring buildings (not the target): {p.neighbour_signs or 'none'}."
        )
        return state, {"street_level": p.street_level, "sign": p.center_sign, "neighbour_signs": p.neighbour_signs}
    p3 = parse_caption(cap_text)
    state = text + "\nStreet photo (2026, cut from a panorama; may show a neighbouring building), described by a vision model: " + cap_text
    return state, {"street_level": p3.street_level, "sign": p3.sign, "neighbour_signs": None}


def run_variant(name: str, rows, vlm, client, questions) -> None:
    tight, prompt = VARIANTS[name]
    t0 = time.perf_counter()
    out = []
    for i, r in enumerate(rows, 1):
        bid, image_id, heading, bearing, dist = r[0], r[1], r[2], r[3], r[4]
        fov = fov_for_frontage(r[12], dist) if tight else 80.0
        path, roll = make_crop(bid, image_id, heading, bearing, fov)
        cap = caption(vlm, path, CAPTION_PROMPTS[prompt])
        state, parsed = tier1_state(r[8], cap.text, prompt)
        res = ask(client, state, questions)
        a = {x.question: x for x in res.answers}
        out.append({
            "building_id": bid, "truth": r[5], "food": r[6], "split": r[7], "has_photo": r[11], "dist_m": round(dist, 1),
            "fov": round(fov, 1), "roll": round(roll, 1), "caption": cap.text, **parsed,
            "t0_comm": r[9]["commercial"] + r[9]["mixed-use"], "t0_food": r[9]["food"], "stack_comm": r[10]["commercial"] + r[10]["mixed-use"],
            "t1_comm": a["d1"].probs["commercial"] + a["d1"].probs["mixed-use"], "t1_food": a["d3"].probs["yes"], "d5": a["d5"].probs["yes"],
        })
        if i % 20 == 0:
            print(f"  [{name}] {i}/{len(rows)} ({(time.perf_counter() - t0) / 60:.1f} min)", flush=True)
            Path(f"data/pano_pilot_{name}.json").write_text(json.dumps(out, indent=1))
    Path(f"data/pano_pilot_{name}.json").write_text(json.dumps(out, indent=1))
    print(f"[{name}] done in {(time.perf_counter() - t0) / 60:.1f} min", flush=True)


def main(names: list[str]) -> None:
    CROPS.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT b.id, p.image_id, p.heading_deg, p.bearing_deg, p.dist_m, g.d1_class, g.d3_food, g.split, e.text,
                   j.probs, s.probs, (ip.building_id IS NOT NULL) AS has_photo, (e.payload->'geometry'->>'frontage_width_m')::float
            FROM pano_pick p JOIN building b ON b.id = p.building_id JOIN area a ON a.id = b.area_id AND a.slug = 'east_passyunk'
            JOIN ground_truth g ON g.building_id = b.id JOIN evidence e ON e.building_id = b.id AND e.tier = 0
            JOIN baseline_prediction j ON j.building_id = b.id AND j.baseline = 'jev-p1'
            JOIN baseline_prediction s ON s.building_id = b.id AND s.baseline = 'stack-gbm'
            LEFT JOIN image_pick ip ON ip.building_id = b.id
            ORDER BY b.id
            """
        ).fetchall()
    print(f"{len(rows)} East Passyunk buildings with a panorama pick; variants: {names}", flush=True)
    vlm, client, questions = load_vlm(), make_client(), build_tier1_questions("p1")
    for name in names:
        run_variant(name, rows, vlm, client, questions)


if __name__ == "__main__":
    main(sys.argv[1:] or ["tight-v4"])
