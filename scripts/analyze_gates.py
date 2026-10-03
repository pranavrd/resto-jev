"""Which escalation gate recovers the most commercial buildings for the least escalation?

Upper-bound analysis, not the cascade: escalated buildings are assumed to be resolved perfectly by imagery,
everything else keeps Jev's answer. It compares gates (scores that rank buildings for escalation) at equal
escalation rates, over all 3,795 buildings. Gradient-boosted scores are out-of-fold (train, dev) or from
the final model (test), so none are in-sample. Run: .venv/bin/python scripts/analyze_gates.py
"""

from streetwalker import db

COMM = ("commercial", "mixed-use")
RATES = (0.05, 0.10, 0.15, 0.20, 0.30)


def main() -> None:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT g.d1_class, j.d1_class, j.confidence, j.probs, f.probs, e.payload
            FROM ground_truth g
            JOIN baseline_prediction j ON j.building_id = g.building_id AND j.baseline = 'jev-p1'
            JOIN baseline_prediction f ON f.building_id = g.building_id AND f.baseline = 'gbm-full'
            JOIN evidence e ON e.building_id = g.building_id AND e.tier = 0
            """
        ).fetchall()
    n = len(rows)
    truth = [r[0] in COMM for r in rows]
    jev_pos = [r[1] in COMM for r in rows]
    jev_conf = [r[2] for r in rows]
    jev_risk = [r[3]["commercial"] + r[3]["mixed-use"] for r in rows]
    gbm_risk = [r[4]["commercial"] + r[4]["mixed-use"] for r in rows]
    silent = [not (r[5]["pois"] or "use_tags" in r[5]["osm"] or "name" in r[5]["osm"]) for r in rows]
    total_pos = sum(truth)
    base_tp = sum(t and p for t, p in zip(truth, jev_pos, strict=True))
    print(f"{n} buildings, {total_pos} commercial-or-mixed. Jev alone: recall {base_tp / total_pos:.2f}, precision {base_tp / sum(jev_pos):.2f}")
    print(f"silent buildings: {sum(silent)} ({sum(silent) / n:.0%}); commercial-or-mixed among them: {sum(t for t, s in zip(truth, silent, strict=True) if s)}\n")

    gates = {
        "Jev low confidence": [1 - c for c in jev_conf],
        "Jev risk (non-commercial answers only)": [0 if p else r for p, r in zip(jev_pos, jev_risk, strict=True)],
        "GBM risk (Jev non-commercial only)": [0 if p else r for p, r in zip(jev_pos, gbm_risk, strict=True)],
        "mean of Jev and GBM risk (Jev non-comm.)": [0 if p else (a + b) / 2 for p, a, b in zip(jev_pos, jev_risk, gbm_risk, strict=True)],
        "silent AND GBM risk (Jev non-comm.)": [0 if (p or not s) else r for p, s, r in zip(jev_pos, silent, gbm_risk, strict=True)],
    }
    print(f"{'gate':44s} " + " ".join(f"{int(r * 100):>3d}% esc: recall/prec" for r in RATES))
    for name, score in gates.items():
        order = sorted(range(n), key=lambda i: -score[i])
        cells = []
        for rate in RATES:
            esc = set(order[: int(rate * n)])
            tp = sum(truth[i] for i in esc) + sum(truth[i] and jev_pos[i] for i in range(n) if i not in esc)
            pred_pos = sum(truth[i] for i in esc) + sum(jev_pos[i] for i in range(n) if i not in esc)
            cells.append(f"{tp / total_pos:.2f}/{tp / pred_pos:.2f}")
        print(f"{name:44s} " + "  ".join(f"{c:>16s}" for c in cells))


if __name__ == "__main__":
    main()
