"""Ranking quality of each Tier 0 predictor, and which escalation gate recovers the most commercial buildings.

Part 1 compares threshold-free ranking of commercial-or-mixed (AUROC, average precision).
Part 2 is an upper-bound escalation analysis, not the cascade: escalated buildings are assumed to be resolved
perfectly by imagery, everything else keeps the Tier 0 predictor's own answer. Gates (scores that rank buildings
for escalation) are compared at equal escalation rates over all 3,795 buildings. Learned scores are out-of-fold
(train, dev) or from the final model (test), so none are in-sample; Jev needs no training.
Run: .venv/bin/python scripts/analyze_gates.py
"""

from sklearn.metrics import average_precision_score, roc_auc_score

from streetwalker import db

COMM = ("commercial", "mixed-use")
RATES = (0.05, 0.10, 0.15, 0.20, 0.30)
PREDICTORS = ("jev-p1", "stack-lr", "stack-gbm", "gbm-full")


def risk(probs: dict) -> float:
    return probs["commercial"] + probs["mixed-use"]


def main() -> None:
    with db.connect() as conn:
        base = conn.execute("SELECT g.building_id, g.d1_class, g.split FROM ground_truth g ORDER BY g.building_id").fetchall()
        preds = {}
        for name in PREDICTORS:
            preds[name] = {
                r[0]: (r[1], r[2], r[3])
                for r in conn.execute(
                    "SELECT building_id, d1_class, confidence, probs FROM baseline_prediction WHERE baseline = %s", (name,))
            }
    ids = [b[0] for b in base]
    truth = [b[1] in COMM for b in base]
    n, total_pos = len(ids), sum(truth)

    print(f"{n} buildings, {total_pos} commercial-or-mixed\n")
    print("Part 1: ranking quality of p(commercial) + p(mixed-use), threshold-free")
    print(f"  {'predictor':12s} {'AUROC':>6s} {'AP':>6s}")
    for name in PREDICTORS:
        s = [risk(preds[name][i][2]) for i in ids]
        print(f"  {name:12s} {roc_auc_score(truth, s):6.3f} {average_precision_score(truth, s):6.3f}")

    print("\nPart 2: commercial-or-mixed recall / precision after escalating the top x% of buildings (oracle imagery)")
    print(f"  {'predictor, gate':40s} " + " ".join(f"{int(r * 100):>3d}% esc" + " " * 6 for r in RATES))
    for name in PREDICTORS:
        pos = [preds[name][i][0] in COMM for i in ids]
        conf = [preds[name][i][1] for i in ids]
        rk = [risk(preds[name][i][2]) for i in ids]
        gates = {
            f"{name}, low confidence": [1 - c for c in conf],
            f"{name}, hidden risk": [0 if p else r for p, r in zip(pos, rk, strict=True)],
        }
        if name == "stack-lr":
            jev_rk = [risk(preds["jev-p1"][i][2]) for i in ids]
            gates["stack-lr + Jev, mean hidden risk"] = [0 if p else (a + b) / 2 for p, a, b in zip(pos, rk, jev_rk, strict=True)]
        for label, score in gates.items():
            order = sorted(range(n), key=lambda i: -score[i])
            cells = []
            for rate in RATES:
                esc = set(order[: int(rate * n)])
                tp = sum(truth[i] for i in esc) + sum(truth[i] and pos[i] for i in range(n) if i not in esc)
                pp = sum(truth[i] for i in esc) + sum(pos[i] for i in range(n) if i not in esc)
                cells.append(f"{tp / total_pos:.2f}/{tp / pp:.2f}")
            print(f"  {label:40s} " + "   ".join(f"{c:>9s}" for c in cells))
        print()
    print("Hybrid: Jev's own answer for everything that is not escalated, another model ranks who to escalate")
    jev_pos = [preds["jev-p1"][i][0] in COMM for i in ids]
    jev_rk = [risk(preds["jev-p1"][i][2]) for i in ids]
    for gate_name in ("stack-lr", "stack-gbm", "gbm-full"):
        g_rk = [risk(preds[gate_name][i][2]) for i in ids]
        for label, score in ((f"Jev answers, {gate_name} hidden risk", [0 if p else r for p, r in zip(jev_pos, g_rk, strict=True)]),
                             (f"Jev answers, mean(Jev, {gate_name}) risk", [0 if p else (a + b) / 2 for p, a, b in zip(jev_pos, jev_rk, g_rk, strict=True)])):
            order = sorted(range(n), key=lambda i: -score[i])
            cells = []
            for rate in RATES:
                esc = set(order[: int(rate * n)])
                tp = sum(truth[i] for i in esc) + sum(truth[i] and jev_pos[i] for i in range(n) if i not in esc)
                pp = sum(truth[i] for i in esc) + sum(jev_pos[i] for i in range(n) if i not in esc)
                cells.append(f"{tp / total_pos:.2f}/{tp / pp:.2f}")
            print(f"  {label:40s} " + "   ".join(f"{c:>9s}" for c in cells))
    print()
    print("Part 3: realistic imagery. Only buildings with a usable photo can be escalated, and imagery resolves only a")
    print("fraction r of the commercial ones it is shown (pilot: about 0.45, captions found readable signage on 6 of 14).")
    with db.connect() as conn:
        has_img = {r[0] for r in conn.execute("SELECT building_id FROM image_pick")}
    avail = [i in has_img for i in ids]
    print(f"  buildings with an image: {sum(avail)} ({sum(avail) / n:.0%}); commercial-or-mixed with an image: "
          f"{sum(t and a for t, a in zip(truth, avail, strict=True))} of {total_pos}")
    print(f"  {'gate, resolution r':44s} " + " ".join(f"{int(r * 100):>3d}% esc" + " " * 6 for r in RATES))
    for gate_name, g_score in (
        ("Jev hidden risk", [0 if p else r for p, r in zip(jev_pos, jev_rk, strict=True)]),
        ("mean(Jev, stack-gbm) hidden risk", [0 if p else (a + b) / 2 for p, a, b in zip(
            jev_pos, jev_rk, [risk(preds["stack-gbm"][i][2]) for i in ids], strict=True)]),
    ):
        for r_res in (1.0, 0.45):
            order = sorted((i for i in range(n) if avail[i]), key=lambda i: -g_score[i])
            cells = []
            for rate in RATES:
                esc = set(order[: int(rate * n)])
                tp = sum(truth[i] and jev_pos[i] for i in range(n)) + r_res * sum(truth[i] and not jev_pos[i] for i in esc)
                pp = sum(jev_pos[i] for i in range(n)) + r_res * sum(truth[i] and not jev_pos[i] for i in esc)
                cells.append(f"{tp / total_pos:.2f}/{tp / pp:.2f}")
            print(f"  {gate_name + ', r=' + str(r_res):44s} " + "   ".join(f"{c:>9s}" for c in cells))
    print()
    base_tp = {name: sum(t and preds[name][i][0] in COMM for t, i in zip(truth, ids, strict=True)) for name in PREDICTORS}
    base_pp = {name: sum(preds[name][i][0] in COMM for i in ids) for name in PREDICTORS}
    print("no escalation: " + "; ".join(f"{k} recall {base_tp[k] / total_pos:.2f} precision {base_tp[k] / base_pp[k]:.2f}" for k in PREDICTORS))


if __name__ == "__main__":
    main()
