"""Pilot: panorama crops for East Passyunk. Cut a leveled view toward each building, caption it, ask Jev with the caption.

Needs the panoramas in the local cache (data/images) and image picks (python -m streetwalker.imagery_area).
Run: .venv/bin/python -u scripts/pano_pilot.py
"""

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from streetwalker import db
from streetwalker.images_cache import fetch
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import build_questions
from streetwalker.pano import level_roll, perspective_view
from streetwalker.vlm import CAPTION_PROMPTS, caption, load_vlm, parse_caption

CROPS = Path("data/images/crops")
PROMPT = "v3"


def make_crop(building_id: int, image_id: str, heading: float, bearing: float) -> tuple[str, float]:
    out = CROPS / f"b{building_id}_{image_id}.jpg"
    meta = CROPS / f"b{building_id}_{image_id}.roll"
    if out.exists() and meta.exists():
        return str(out), float(meta.read_text())
    pano = np.asarray(Image.open(fetch(image_id, "original")).convert("RGB"))
    roll = level_roll(pano, heading, bearing)
    Image.fromarray(perspective_view(pano, heading, bearing, roll_deg=roll)).save(out, quality=92)
    meta.write_text(str(roll))
    return str(out), roll


def main() -> None:
    CROPS.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT b.id, p.image_id, p.heading_deg, p.bearing_deg, p.dist_m, g.d1_class, g.d3_food, g.split, e.text,
                   j.probs, s.probs, (ip.building_id IS NOT NULL) AS has_photo
            FROM pano_pick p JOIN building b ON b.id = p.building_id JOIN area a ON a.id = b.area_id AND a.slug = 'east_passyunk'
            JOIN ground_truth g ON g.building_id = b.id JOIN evidence e ON e.building_id = b.id AND e.tier = 0
            JOIN baseline_prediction j ON j.building_id = b.id AND j.baseline = 'jev-p1'
            JOIN baseline_prediction s ON s.building_id = b.id AND s.baseline = 'stack-gbm'
            LEFT JOIN image_pick ip ON ip.building_id = b.id
            ORDER BY b.id
            """
        ).fetchall()
    print(f"{len(rows)} East Passyunk buildings with a panorama pick", flush=True)
    t0 = time.perf_counter()
    crops = [make_crop(r[0], r[1], r[2], r[3]) for r in rows]
    print(f"crops ready in {time.perf_counter() - t0:.0f}s", flush=True)

    vlm = load_vlm()
    client, questions = make_client(), build_questions("p1")
    out = []
    for i, (r, (path, roll)) in enumerate(zip(rows, crops, strict=True), 1):
        cap = caption(vlm, path, CAPTION_PROMPTS[PROMPT])
        parsed = parse_caption(cap.text)
        state = r[8] + "\nStreet photo (2026, cut from a panorama; may show a neighbouring building), described by a vision model: " + cap.text
        res = ask(client, state, questions)
        a = {x.question: x for x in res.answers}
        t0f = r[9]["food"]
        out.append({
            "building_id": r[0], "truth": r[5], "food": r[6], "split": r[7], "has_photo": r[11], "dist_m": round(r[4], 1),
            "roll": round(roll, 1), "caption": cap.text, "street_level": parsed.street_level, "sign": parsed.sign,
            "t0_comm": r[9]["commercial"] + r[9]["mixed-use"], "t0_food": t0f,
            "stack_comm": r[10]["commercial"] + r[10]["mixed-use"],
            "t1_comm": a["d1"].probs["commercial"] + a["d1"].probs["mixed-use"], "t1_food": a["d3"].probs["yes"],
        })
        if i % 20 == 0:
            print(f"  {i}/{len(rows)} captioned ({(time.perf_counter() - t0) / 60:.1f} min elapsed)", flush=True)
            Path("data/pano_pilot.json").write_text(json.dumps(out, indent=1))
    Path("data/pano_pilot.json").write_text(json.dumps(out, indent=1))
    print("done", flush=True)


if __name__ == "__main__":
    main()
