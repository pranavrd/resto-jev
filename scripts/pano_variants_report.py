"""Compare panorama-crop variants on the 136 East Passyunk buildings.
Run: .venv/bin/python scripts/pano_variants_report.py [variant ...]   (default: every file in data/)
"""

import json
import sys
from pathlib import Path

from sklearn.metrics import average_precision_score, roc_auc_score

from streetwalker.vlm import parse_caption, parse_caption_v4

COMM = ("commercial", "mixed-use")
FILES = {"wide-v3": "data/pano_pilot.json", "tight-v3": "data/pano_pilot_tight-v3.json", "tight-v4": "data/pano_pilot_tight-v4.json"}


def counts(truth, pred):
    tp = sum(t and p for t, p in zip(truth, pred, strict=True))
    fp = sum((not t) and p for t, p in zip(truth, pred, strict=True))
    fn = sum(t and (not p) for t, p in zip(truth, pred, strict=True))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return tp, fp, fn, p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main(names: list[str]) -> None:
    data = {n: json.loads(Path(FILES[n]).read_text()) for n in names if Path(FILES[n]).exists()}
    for n, rows in data.items():  # re-parse signs from the raw captions so parser fixes apply to old runs
        for r in rows:
            r["sign"] = parse_caption_v4(r["caption"]).center_sign if n.endswith("v4") else parse_caption(r["caption"]).sign
    base = next(iter(data.values()))
    truth = [r["truth"] in COMM for r in base]
    print(f"{len(base)} buildings ({sum(truth)} commercial or mixed, {len(truth) - sum(truth)} other)\n")

    print("A. Sign text attributed to the target building")
    print(f"  {'variant':10s} {'on comm/mixed':>14s} {'on other (false)':>17s} {'precision of a sign':>20s}")
    for n, rows in data.items():
        pos = [r for r in rows if r["truth"] in COMM]
        neg = [r for r in rows if r["truth"] not in COMM]
        sp, sn = sum(bool(r["sign"]) for r in pos), sum(bool(r["sign"]) for r in neg)
        print(f"  {n:10s} {sp:4d}/{len(pos)} ({sp / len(pos):4.0%}) {sn:6d}/{len(neg)} ({sn / len(neg):4.0%}) {sp / max(sp + sn, 1):19.0%}")

    print("\nB. Commercial-or-mixed with the caption (Jev p >= 0.5)")
    print(f"  {'':34s} {'TP':>3s} {'FP':>3s} {'FN':>3s}    P    R   F1  AUROC    AP")
    ref = base
    rows_out = [("Jev tier 0 (no imagery)", [r["t0_comm"] for r in ref]), ("stack-gbm (no imagery)", [r["stack_comm"] for r in ref])]
    for n, rows in data.items():
        rows_out.append((f"{n}: caption always used", [r["t1_comm"] for r in rows]))
        if "d5" in rows[0]:
            rows_out.append((f"{n}: caption used only if D5 >= 0.5", [r["t1_comm"] if r["d5"] >= 0.5 else r["t0_comm"] for r in rows]))
            rows_out.append((f"{n}: max(stack, caption, D5-gated)", [max(r["stack_comm"], r["t1_comm"] if r["d5"] >= 0.5 else 0.0) for r in rows]))
    for label, score in rows_out:
        tp, fp, fn, p, r, f = counts(truth, [s >= 0.5 for s in score])
        print(f"  {label:34s} {tp:3d} {fp:3d} {fn:3d}  {p:.2f} {r:.2f} {f:.2f}  {roc_auc_score(truth, score):.3f} {average_precision_score(truth, score):.3f}")

    print("\nC. D5 (does the description report something on the target building itself?)")
    for n, rows in data.items():
        if "d5" not in rows[0]:
            continue
        pos = [r["d5"] for r in rows if r["truth"] in COMM]
        neg = [r["d5"] for r in rows if r["truth"] not in COMM]
        yes_pos = sum(x >= 0.5 for x in pos)
        yes_neg = sum(x >= 0.5 for x in neg)
        print(f"  {n:10s} mean D5 on comm/mixed {sum(pos) / len(pos):.2f}, on other {sum(neg) / max(len(neg), 1):.2f}; "
              f"D5>=0.5 on {yes_pos}/{len(pos)} comm/mixed and {yes_neg}/{len(neg)} other; AUROC of D5 itself "
              f"{roc_auc_score(truth, [r['d5'] for r in rows]):.3f}")

    print("\nD. Rescue of the stacker's misses (commercial or mixed that stack-gbm scores below 0.5)")
    for n, rows in data.items():
        miss = [r for r in rows if r["truth"] in COMM and r["stack_comm"] < 0.5]
        gate = (lambda r: r["d5"] >= 0.5) if "d5" in rows[0] else (lambda r: True)
        rescued = [r for r in miss if r["t1_comm"] >= 0.5 and gate(r)]
        new_fp = [r for r in rows if r["truth"] not in COMM and r["stack_comm"] < 0.5 and r["t1_comm"] >= 0.5 and gate(r)]
        print(f"  {n:10s} {len(rescued)} of {len(miss)} misses rescued; {len(new_fp)} new false positives")


if __name__ == "__main__":
    main(sys.argv[1:] or list(FILES))
