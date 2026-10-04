"""Pilot: do vision-model captions help or mislead Jev on a handful of buildings?

For each building in data/vlm_test_set.json: caption its chosen photo with a prompt version, append the caption to
the tier-0 evidence text, and ask Jev the same D1 to D3 questions (prompt p1). Tiny sample (about 20): a sanity
check on direction and failure modes, not a measurement. Run: .venv/bin/python scripts/vlm_pilot.py v3 [keep_fraction_of_lower_image, e.g. 0.55]
"""

import json
import sys
from pathlib import Path

from PIL import Image

from streetwalker import db
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import build_questions
from streetwalker.vlm import CAPTION_PROMPTS, caption, load_vlm

COMM = ("commercial", "mixed-use")


def state_with_caption(text: str, cap: str, year: int) -> str:
    return (text + f"\nStreet photo ({year}, may show a neighbouring building or be out of date), described by a vision model: " + cap)


def crop_lower(path: str, keep: float) -> str:
    """Keep the lower `keep` fraction of the photo. Windshield cameras tilt up, so ground floors sit at the bottom."""
    out = Path(path).with_name(Path(path).stem + f"_lower{int(keep * 100)}.jpg")
    if not out.exists():
        im = Image.open(path)
        w, h = im.size
        im.crop((0, int(h * (1 - keep)), w, h)).save(out, quality=92)
    return str(out)


def main(version: str, keep: float | None) -> None:
    with open("data/vlm_test_set.json") as f:
        items = json.load(f)
    vlm = load_vlm()
    client, questions = make_client(), build_questions("p1")
    with db.connect() as conn:
        texts = dict(conn.execute("SELECT building_id, text FROM evidence WHERE tier = 0 AND building_id = ANY(%s)",
                                  ([i["building_id"] for i in items],)).fetchall())
        tier0 = {r[0]: r[1] for r in conn.execute(
            "SELECT building_id, probs FROM baseline_prediction WHERE baseline = 'jev-p1' AND building_id = ANY(%s)",
            ([i["building_id"] for i in items],))}
    rows = []
    for it in items:
        cap = caption(vlm, crop_lower(it["path"], keep) if keep else it["path"], CAPTION_PROMPTS[version])
        r = ask(client, state_with_caption(texts[it["building_id"]], cap.text, it["year"]), questions)
        a = {x.question: x for x in r.answers}
        p0 = tier0[it["building_id"]]
        rows.append({
            "building_id": it["building_id"], "label": it["label"], "truth": it["d1"], "food": it["food"], "caption": cap.text,
            "t0_comm": p0["commercial"] + p0["mixed-use"], "t0_food": p0["food"],
            "t1_d1": a["d1"].answer, "t1_comm": a["d1"].probs["commercial"] + a["d1"].probs["mixed-use"],
            "t1_food": a["d3"].probs["yes"], "t1_d2": a["d2"].answer,
        })
    with open(f"data/vlm_pilot_{version}{'_lower' + str(int(keep * 100)) if keep else ''}.json", "w") as f:
        json.dump(rows, f, indent=1)
    print(f"{'bldg':>5s} {'truth':11s} food | tier0 p(comm) -> with caption p(comm) | food p: t0 -> t1 | caption")
    for r in rows:
        mark = "+" if (r["t1_comm"] >= 0.5) == (r["truth"] in COMM) else "x"
        print(f"{r['building_id']:5d} {r['truth']:11s} {'F' if r['food'] else '-'}    |   {r['t0_comm']:.2f}  ->  {r['t1_comm']:.2f} {mark}          |   {r['t0_food']:.2f} -> {r['t1_food']:.2f} | {r['caption'][:95]}")
    right0 = sum((r["t0_comm"] >= 0.5) == (r["truth"] in COMM) for r in rows)
    right1 = sum((r["t1_comm"] >= 0.5) == (r["truth"] in COMM) for r in rows)
    print(f"\ncommercial-any correct at p>=0.5: tier 0 {right0}/{len(rows)}  ->  with caption {right1}/{len(rows)}")
    pos = [r for r in rows if r["truth"] in COMM]
    neg = [r for r in rows if r["truth"] not in COMM]
    print(f"  on commercial/mixed ({len(pos)}): mean p(comm) {sum(r['t0_comm'] for r in pos)/len(pos):.2f} -> {sum(r['t1_comm'] for r in pos)/len(pos):.2f}")
    print(f"  on residential ({len(neg)}):      mean p(comm) {sum(r['t0_comm'] for r in neg)/len(neg):.2f} -> {sum(r['t1_comm'] for r in neg)/len(neg):.2f}")
    food = [r for r in rows if r["food"]]
    print(f"  food-licensed ({len(food)}): mean p(food) {sum(r['t0_food'] for r in food)/len(food):.2f} -> {sum(r['t1_food'] for r in food)/len(food):.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "v3", float(sys.argv[2]) if len(sys.argv) > 2 else None)
