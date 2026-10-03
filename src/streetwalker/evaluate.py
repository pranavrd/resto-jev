"""Score stored baseline predictions against ground truth.

Usage: python -m streetwalker.evaluate [--baseline rules-v1] [--split dev] [--area SLUG] [--status all|agree]

Defaults to the dev split. The test split is frozen: using it requires --final and is logged to
docs/test-set-log.md, so test numbers are looked at deliberately and rarely.
"""

import argparse
import datetime as dt
import sys
from collections import Counter, defaultdict

from streetwalker import db
from streetwalker.bootstrap import grouped_bootstrap
from streetwalker.calibration import ece, reliability_bins
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.metrics import accuracy, binary, confusion, macro_f1, per_class

SPLITS = {"train": ("train",), "dev": ("dev",), "trainval": ("train", "dev"), "test": ("test",), "heldout": ("dev", "test"), "all": ("train", "dev", "test")}
LOG = db.ROOT / "docs" / "test-set-log.md"


def load(conn, baseline: str, splits: tuple[str, ...], area: str | None, status: str):
    sql = """
        SELECT a.slug, g.d1_class, g.d3_food, g.label_status, g.split, p.d1_class, p.d3_food, p.rule, p.confidence, g.group_key
        FROM ground_truth g JOIN baseline_prediction p ON p.building_id = g.building_id AND p.baseline = %s
        JOIN building b ON b.id = g.building_id JOIN area a ON a.id = b.area_id
        WHERE g.split = ANY(%s)"""
    args: list = [baseline, list(splits)]
    if area:
        sql += " AND a.slug = %s"
        args.append(area)
    if status == "agree":
        sql += " AND g.label_status IN ('agree', 'land_use_only')"  # drop only the disputed labels
    return conn.execute(sql + " ORDER BY g.building_id", args).fetchall()


def fmt_row(label: str, s) -> str:
    return f"  {label:20s} {s.support:6d} {s.predicted:6d}   {s.precision:5.2f} {s.recall:5.2f} {s.f1:5.2f}"


def report(rows: list, title: str) -> None:
    truth = [r[1] for r in rows]
    pred = [r[5] for r in rows]
    stats = per_class(truth, pred, list(D1_CLASSES))
    majority = Counter(truth).most_common(1)[0]
    print(f"\n== {title}: n={len(rows)}")
    print(f"D1 accuracy {accuracy(truth, pred):.3f}  macro-F1 {macro_f1(stats):.3f}  (always '{majority[0]}': {majority[1] / len(rows):.3f})")
    print(f"  {'class':20s} {'true':>6s} {'pred':>6s}   {'P':>5s} {'R':>5s} {'F1':>5s}")
    for s in stats:
        print(fmt_row(s.label, s))

    cm = confusion(truth, pred)
    short = {c: c[:5] for c in D1_CLASSES}
    print("  confusion (rows = truth, columns = prediction)")
    print("  " + " " * 20 + " ".join(f"{short[c]:>6s}" for c in D1_CLASSES))
    for t in D1_CLASSES:
        if any(cm[(t, p)] for p in D1_CLASSES):
            print(f"  {t:20s} " + " ".join(f"{cm[(t, p)]:6d}" for p in D1_CLASSES))

    commercial = {"commercial", "mixed-use"}
    comm = binary([t in commercial for t in truth], [p in commercial for p in pred])
    print(f"commercial-any (commercial or mixed-use): P {comm.precision:.2f} R {comm.recall:.2f} F1 {comm.f1:.2f} (n_true={comm.support})")
    food = binary([r[2] for r in rows], [r[6] for r in rows])
    print(f"D3 food-serving (licence truth):           P {food.precision:.2f} R {food.recall:.2f} F1 {food.f1:.2f} (n_true={food.support})")

    conf = [r[8] for r in rows]
    if all(c is not None for c in conf):
        correct = [t == p for t, p in zip(truth, pred, strict=True)]
        print(f"D1 calibration: ECE {ece(conf, correct):.3f}")
        for b in reliability_bins(conf, correct, 10):
            print(f"  confidence {b.lo:.1f}-{b.hi:.1f}: n={b.n:5d}  mean confidence {b.mean_confidence:.2f}  accuracy {b.accuracy:.2f}")

    by_rule: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by_rule[r[7]].append(r[1] == r[5])
    print("  rule                                    fired  correct")
    for rule, hits in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
        print(f"  {rule:38s} {len(hits):6d}   {sum(hits) / len(hits):5.2f}")


def compare(conn, baselines: list[str], split: str, area: str | None, status: str) -> None:
    print(f"split={split} area={area or 'all'} labels={status}")
    print(f"{'baseline':13s} {'n':>5s} {'D1 acc':>7s} {'macroF1':>8s} | commercial-any P    R   F1 | D3 food P    R   F1 |   ECE")
    for name in baselines:
        rows = load(conn, name, SPLITS[split], area, status)
        truth, pred = [r[1] for r in rows], [r[5] for r in rows]
        stats = per_class(truth, pred, list(D1_CLASSES))
        commercial = {"commercial", "mixed-use"}
        c = binary([t in commercial for t in truth], [p in commercial for p in pred])
        f = binary([r[2] for r in rows], [r[6] for r in rows])
        conf = [r[8] for r in rows]
        calib = f"{ece(conf, [t == p for t, p in zip(truth, pred, strict=True)]):6.3f}" if all(c is not None for c in conf) else "     -"
        print(f"{name:13s} {len(rows):5d} {accuracy(truth, pred):7.3f} {macro_f1(stats):8.3f} | {'':15s}{c.precision:4.2f} {c.recall:4.2f} {c.f1:4.2f} | {'':9s}{f.precision:4.2f} {f.recall:4.2f} {f.f1:4.2f} | {calib}")


COMMERCIAL = {"commercial", "mixed-use"}


def _comm_f1(rows: list[tuple[bool, bool]]) -> float:
    return binary([t for t, _ in rows], [p for _, p in rows]).f1


def _acc(rows: list[tuple[str, str]]) -> float:
    return sum(t == p for t, p in rows) / len(rows) if rows else 0.0


def compare_bootstrap(conn, baselines: list[str], split: str, area: str | None, status: str, n: int) -> None:
    """95% street-grouped intervals for each baseline, and paired F1 differences against the first one."""
    loaded = {b: load(conn, b, SPLITS[split], area, status) for b in baselines}
    base = loaded[baselines[0]]
    print(f"\nstreet-grouped bootstrap, {n} resamples, 95% intervals; difference is paired vs {baselines[0]}")
    print(f"{'baseline':13s} {'D1 acc':>22s} {'commercial-any F1':>24s} {'F1 difference':>24s}")
    for name, rows in loaded.items():
        groups = [r[9] for r in rows]
        acc_pairs = [(r[1], r[5]) for r in rows]
        f1_pairs = [(r[1] in COMMERCIAL, r[5] in COMMERCIAL) for r in rows]
        alo, ahi = grouped_bootstrap(acc_pairs, groups, _acc, n)
        flo, fhi = grouped_bootstrap(f1_pairs, groups, _comm_f1, n)
        diff = "-"
        if name != baselines[0]:
            triples = [(r[1] in COMMERCIAL, r[5] in COMMERCIAL, q[5] in COMMERCIAL) for r, q in zip(rows, base, strict=True)]

            def delta(ts):
                return binary([t for t, _, _ in ts], [p for _, p, _ in ts]).f1 - binary([t for t, _, _ in ts], [q for _, _, q in ts]).f1

            point = delta(triples)
            dlo, dhi = grouped_bootstrap(triples, groups, delta, n)
            diff = f"{point:+.2f} [{dlo:+.2f}, {dhi:+.2f}]"
        print(f"{name:13s} {_acc(acc_pairs):6.3f} [{alo:.3f}, {ahi:.3f}]   {_comm_f1(f1_pairs):5.2f} [{flo:.2f}, {fhi:.2f}]   {diff:>24s}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="rules-v1")
    ap.add_argument("--split", default="dev", choices=list(SPLITS))
    ap.add_argument("--area")
    ap.add_argument("--status", default="all", choices=["all", "agree"])
    ap.add_argument("--final", action="store_true", help="required to touch the frozen test split")
    ap.add_argument("--compare", nargs="+", metavar="BASELINE", help="one summary row per baseline instead of the full report")
    ap.add_argument("--bootstrap", type=int, metavar="N", help="with --compare: street-grouped bootstrap intervals (N resamples)")
    args = ap.parse_args()

    if "test" in SPLITS[args.split]:
        if not args.final:
            sys.exit("The test split is frozen. Re-run with --final once the baseline is done being tuned.")
        stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
        with LOG.open("a") as f:
            names = ", ".join(args.compare) if args.compare else args.baseline
            f.write(f"| {stamp} | {names} | {args.split} | {args.area or 'all areas'} | {args.status} |\n")
        print("*** TEST SPLIT (frozen) ***  logged to docs/test-set-log.md")

    if args.compare:
        with db.connect() as conn:
            compare(conn, args.compare, args.split, args.area, args.status)
            if args.bootstrap:
                compare_bootstrap(conn, args.compare, args.split, args.area, args.status, args.bootstrap)
        return

    with db.connect() as conn:
        rows = load(conn, args.baseline, SPLITS[args.split], args.area, args.status)
        if not rows:
            sys.exit("No rows: run baseline_area and groundtruth_area first.")
        print(f"baseline={args.baseline} split={args.split} area={args.area or 'all'} labels={args.status}")
        report(rows, "all areas" if not args.area else args.area)
        if not args.area:
            for slug in sorted({r[0] for r in rows}):
                sub = [r for r in rows if r[0] == slug]
                truth, pred = [r[1] for r in sub], [r[5] for r in sub]
                commercial = {"commercial", "mixed-use"}
                c = binary([t in commercial for t in truth], [p in commercial for p in pred])
                print(f"  {slug:14s} n={len(sub):4d} acc={accuracy(truth, pred):.3f} commercial-any P {c.precision:.2f} R {c.recall:.2f} F1 {c.f1:.2f}")


if __name__ == "__main__":
    main()
