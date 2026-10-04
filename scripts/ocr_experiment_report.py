"""Summarise data/ocr_experiment.json. Run: .venv/bin/python scripts/ocr_experiment_report.py"""

import json

from sklearn.metrics import average_precision_score, roc_auc_score

from streetwalker.ocr import name_match
from streetwalker.vlm import parse_caption_v4

COMM = ("commercial", "mixed-use")


def any_name(texts: list[str], names: list[str]) -> bool:
    return any(name_match(texts, n) for n in names)


def main() -> None:
    with open("data/ocr_experiment.json") as f:
        rows = json.load(f)
    with open("data/pano_pilot_tight-v4.json") as f:  # re-parse from the raw captions so parser fixes apply
        vlm = {r["building_id"]: parse_caption_v4(r["caption"]) for r in json.load(f)}
    for r in rows:
        r["vlm_sign"], r["vlm_neighbours"] = vlm[r["building_id"]].center_sign, vlm[r["building_id"]].neighbour_signs
    truth = [r["truth"] in COMM for r in rows]
    pos, neg = [r for r in rows if r["truth"] in COMM], [r for r in rows if r["truth"] not in COMM]
    named = [r for r in rows if r["names"]]
    print(f"{len(rows)} buildings ({len(pos)} commercial or mixed); {len(named)} have a licensed business name within 10 m\n")

    print("A. Does the text spell part of a licensed business name? (only buildings with a name; centre of the picture)")
    print("   a hit on a building whose neighbour holds the licence is possible, so read this as relative, not absolute")
    for label in ("native x2", "1024 view"):
        hit = sum(any_name(r[label]["centre"], r["names"]) for r in named)
        hit_all = sum(any_name(r[label]["centre"] + r[label]["sides"], r["names"]) for r in named)
        print(f"   OCR {label:10s}: centre {hit}/{len(named)} ({hit / len(named):.0%}); anywhere in the picture {hit_all}/{len(named)} ({hit_all / len(named):.0%})")
    vlm_hit = sum(bool(r["vlm_sign"]) and any_name([r["vlm_sign"]], r["names"]) for r in named)
    vlm_any = sum(any_name([t for t in (r["vlm_sign"], r["vlm_neighbours"]) if t], r["names"]) for r in named)
    print(f"   VLM tight-v4  : centre sign {vlm_hit}/{len(named)} ({vlm_hit / len(named):.0%}); incl. neighbour signs {vlm_any}/{len(named)} ({vlm_any / len(named):.0%})\n")

    print("B. Candidate sign text at the centre of the picture")
    for label in ("native x2", "1024 view"):
        sp = sum(bool(r[label]["centre"]) for r in pos)
        sn = sum(bool(r[label]["centre"]) for r in neg)
        print(f"   OCR {label:10s}: commercial/mixed {sp}/{len(pos)} ({sp / len(pos):.0%}), other {sn}/{len(neg)} ({sn / len(neg):.0%})")
    vp = sum(bool(r["vlm_sign"]) for r in pos)
    vn = sum(bool(r["vlm_sign"]) for r in neg)
    print(f"   VLM tight-v4  : commercial/mixed {vp}/{len(pos)} ({vp / len(pos):.0%}), other {vn}/{len(neg)} ({vn / len(neg):.0%})\n")

    print("C. Jev with the OCR text (native x2), commercial-or-mixed at p >= 0.5")
    print(f"   {'':26s} {'TP':>3s} {'FP':>3s} {'FN':>3s}    P    R    F1  AUROC    AP")
    for label, key in (("Jev tier 0", "t0_comm"), ("Jev + OCR text", "t1_comm"), ("stack-gbm (no imagery)", "stack_comm")):
        pred = [r[key] >= 0.5 for r in rows]
        tp = sum(a and b for a, b in zip(truth, pred, strict=True))
        fp = sum((not a) and b for a, b in zip(truth, pred, strict=True))
        fn = sum(a and (not b) for a, b in zip(truth, pred, strict=True))
        p, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        scores = [r[key] for r in rows]
        print(f"   {label:26s} {tp:3d} {fp:3d} {fn:3d}  {p:.2f} {rc:.2f} {2 * p * rc / max(p + rc, 1e-9):.2f}  {roc_auc_score(truth, scores):.3f} {average_precision_score(truth, scores):.3f}")
    miss = [r for r in pos if r["stack_comm"] < 0.5]
    rescued = [r for r in miss if r["t1_comm"] >= 0.5]
    new_fp = [r for r in neg if r["stack_comm"] < 0.5 <= r["t1_comm"]]
    print(f"   stack-gbm misses {len(miss)} commercial/mixed here; OCR text lifts {len(rescued)} of them to p>=0.5 (new false positives among the rest: {len(new_fp)})")
    print("   rescued buildings' centre text:", [r["native x2"]["centre"][:2] for r in rescued][:6])
    print("   examples of centre text on OTHER buildings:", [r["native x2"]["centre"][:2] for r in neg if r["native x2"]["centre"]][:6])
    print("   examples of centre text on commercial/mixed:", [r["native x2"]["centre"][:2] for r in pos if r["native x2"]["centre"]][:8])


if __name__ == "__main__":
    main()
