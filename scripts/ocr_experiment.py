"""OCR experiment on the 136 East Passyunk panorama crops.

Reads text with Apple Vision from two renderings of each crop, scores it (and the VLM caption from tight-v4)
against the licensed business names near each building, and asks Jev with the OCR text added.
Run: .venv/bin/python -u scripts/ocr_experiment.py
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from streetwalker import db
from streetwalker.imagery import fov_for_frontage
from streetwalker.images_cache import fetch
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import build_questions
from streetwalker.ocr import read_text, split_by_position
from streetwalker.pano import level_roll, perspective_view

PX_PER_DEG = 5376 / 360  # the panorama's native angular resolution
NOT_BUSINESS = ("Rental", "Dumpster", "Vacant", "Lodging", "High Rise", "Hazardous", "Sidewalk", "Vendor")


def renderings(pano, heading, bearing, fov, roll):
    native_w = int(fov * PX_PER_DEG)
    native = Image.fromarray(perspective_view(pano, heading, bearing, fov_deg=fov, roll_deg=roll, out_w=native_w, out_h=int(native_w * 0.75)))
    return {"native x2": native.resize((native.width * 2, native.height * 2), Image.LANCZOS),
            "1024 view": Image.fromarray(perspective_view(pano, heading, bearing, fov_deg=fov, roll_deg=roll))}


def main() -> None:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT b.id, p.image_id, p.heading_deg, p.bearing_deg, p.dist_m, g.d1_class, e.text,
                   (e.payload->'geometry'->>'frontage_width_m')::float, j.probs, s.probs,
                   ARRAY(SELECT DISTINCT l.business_name FROM business_license l
                         WHERE l.licensestatus = 'Active' AND l.business_name IS NOT NULL
                           AND ST_DWithin(ST_Transform(l.geom, 32618), ST_Transform(b.geom, 32618), 10)
                           AND l.licensetype !~ %s)
            FROM pano_pick p JOIN building b ON b.id = p.building_id JOIN area a ON a.id = b.area_id AND a.slug = 'east_passyunk'
            JOIN ground_truth g ON g.building_id = b.id JOIN evidence e ON e.building_id = b.id AND e.tier = 0
            JOIN baseline_prediction j ON j.building_id = b.id AND j.baseline = 'jev-p1'
            JOIN baseline_prediction s ON s.building_id = b.id AND s.baseline = 'stack-gbm' ORDER BY b.id
            """, ("|".join(NOT_BUSINESS),)).fetchall()
    vlm = {r["building_id"]: r for r in json.loads(Path("data/pano_pilot_tight-v4.json").read_text())}
    client, questions = make_client(), build_questions("p1")
    out = []
    for i, (bid, img, hd, br, dist, truth, text, width, j, s, names) in enumerate(rows, 1):
        fov = fov_for_frontage(width, dist)
        pano = np.asarray(Image.open(fetch(img, "original")).convert("RGB"))
        roll = level_roll(pano, hd, br, fov_deg=fov)
        rec = {"building_id": bid, "truth": truth, "names": names, "fov": round(fov, 1), "t0_comm": j["commercial"] + j["mixed-use"],
               "stack_comm": s["commercial"] + s["mixed-use"], "vlm_sign": vlm[bid]["sign"], "vlm_neighbours": vlm[bid]["neighbour_signs"]}
        for label, im in renderings(pano, hd, br, fov, roll).items():
            mid, sides = split_by_position(read_text(im))
            rec[label] = {"centre": mid, "sides": sides}
        best = rec["native x2"]
        state = text + "\nText read by OCR from a photo aimed at the target building. At the centre of the picture: " + (
            "; ".join(best["centre"]) or "none") + ". Toward the sides (neighbouring buildings, not the target): " + ("; ".join(best["sides"]) or "none") + "."
        a = {x.question: x for x in ask(client, state, questions).answers}
        rec["t1_comm"] = a["d1"].probs["commercial"] + a["d1"].probs["mixed-use"]
        rec["t1_food"] = a["d3"].probs["yes"]
        out.append(rec)
        if i % 30 == 0:
            print(f"  {i}/{len(rows)}", flush=True)
    Path("data/ocr_experiment.json").write_text(json.dumps(out, indent=1))
    print("done", flush=True)


if __name__ == "__main__":
    main()
