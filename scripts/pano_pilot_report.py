"""Summarise data/pano_pilot.json (written by scripts/pano_pilot.py). Run: .venv/bin/python scripts/pano_pilot_report.py"""

import json
from collections import Counter

from sklearn.metrics import average_precision_score, roc_auc_score

COMM = ("commercial", "mixed-use")


def prf(truth, pred):
    tp = sum(t and p for t, p in zip(truth, pred, strict=True))
    fp = sum((not t) and p for t, p in zip(truth, pred, strict=True))
    fn = sum(t and (not p) for t, p in zip(truth, pred, strict=True))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return tp, fp, fn, p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> None:
    with open("data/pano_pilot.json") as f:
        rows = json.load(f)
    pos = [r for r in rows if r["truth"] in COMM]
    neg = [r for r in rows if r["truth"] not in COMM]
    print(f"{len(rows)} East Passyunk buildings with a panorama crop: {len(pos)} commercial/mixed, {len(neg)} other; {sum(r['has_photo'] for r in rows)} also have an ordinary photo\n")

    print("What the vision model reports at street level:")
    for name, grp in (("commercial/mixed", pos), ("residential/other", neg)):
        c = Counter(r["street_level"] for r in grp)
        print(f"  {name:18s} " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    sign_pos = [r for r in pos if r["sign"]]
    sign_neg = [r for r in neg if r["sign"]]
    print(f"\nreadable sign text on the building: commercial/mixed {len(sign_pos)}/{len(pos)} ({len(sign_pos) / len(pos):.0%}), "
          f"residential/other {len(sign_neg)}/{len(neg)} ({len(sign_neg) / max(len(neg), 1):.0%})")
    print("  examples (commercial/mixed):", [r["sign"] for r in sign_pos[:8]])
    print("  examples (residential/other):", [r["sign"] for r in sign_neg[:8]])

    truth = [r["truth"] in COMM for r in rows]
    print("\ncommercial-any on this subset (p >= 0.5 = positive):")
    print(f"  {'':22s} {'TP':>4s} {'FP':>4s} {'FN':>4s}  {'P':>5s} {'R':>5s} {'F1':>5s}   AUROC  AP")
    for label, key in (("Jev tier 0", "t0_comm"), ("Jev + panorama caption", "t1_comm"), ("stack-gbm (no imagery)", "stack_comm")):
        pred = [r[key] >= 0.5 for r in rows]
        tp, fp, fn, p, r_, f = prf(truth, pred)
        scores = [r[key] for r in rows]
        print(f"  {label:22s} {tp:4d} {fp:4d} {fn:4d}  {p:5.2f} {r_:5.2f} {f:5.2f}   {roc_auc_score(truth, scores):.3f}  {average_precision_score(truth, scores):.3f}")

    shifted = [(r["t1_comm"] - r["t0_comm"]) for r in rows]
    print(f"\nJev p(commercial or mixed) change from the caption: mean on commercial/mixed {sum(r['t1_comm'] - r['t0_comm'] for r in pos) / len(pos):+.3f}, "
          f"mean on other {sum(r['t1_comm'] - r['t0_comm'] for r in neg) / max(len(neg), 1):+.3f}")
    flipped_up = [r for r in rows if r["t0_comm"] < 0.5 <= r["t1_comm"]]
    flipped_dn = [r for r in rows if r["t0_comm"] >= 0.5 > r["t1_comm"]]
    print(f"  flipped to commercial: {len(flipped_up)} ({sum(r['truth'] in COMM for r in flipped_up)} correct); "
          f"flipped to non-commercial: {len(flipped_dn)} ({sum(r['truth'] not in COMM for r in flipped_dn)} correct)")
    print(f"  largest 5 increases: {sorted(shifted)[-5:]}")

    food = [r for r in rows if r["food"]]
    nonfood = [r for r in rows if not r["food"]]
    print(f"\nfood (licence truth, {len(food)} buildings): mean p(food) {sum(r['t0_food'] for r in food) / max(len(food), 1):.2f} -> "
          f"{sum(r['t1_food'] for r in food) / max(len(food), 1):.2f}; other buildings {sum(r['t0_food'] for r in nonfood) / len(nonfood):.2f} -> {sum(r['t1_food'] for r in nonfood) / len(nonfood):.2f}")

    print("\nby whether an ordinary photo also exists:")
    for label, has in (("pano only (new coverage)", False), ("photo also exists (fresher image)", True)):
        sub = [r for r in pos if r["has_photo"] == has]
        if sub:
            print(f"  {label:34s} commercial/mixed n={len(sub):3d}: sign found {sum(bool(r['sign']) for r in sub) / len(sub):.0%}, "
                  f"p(comm) {sum(r['t0_comm'] for r in sub) / len(sub):.2f} -> {sum(r['t1_comm'] for r in sub) / len(sub):.2f}")
    print(f"\nroll chosen by auto-levelling: median {sorted(abs(r['roll']) for r in rows)[len(rows) // 2]:.0f} deg, share at the +/-30 search limit {sum(abs(r['roll']) >= 29 for r in rows) / len(rows):.0%}")


if __name__ == "__main__":
    main()
