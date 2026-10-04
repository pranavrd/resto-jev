"""How well does Jev's aspect scoring agree with a person, and is there a halo?   Usage: .venv/bin/python -m streetwalker.aspect_label_report

PRIVATE: reads review text's labels and Jev's scores derived from Yelp Data. Output stays out of git (docs/private/).

Run it once batch 1 has been labelled. It reads the labels and never writes anything, and nothing in the rating pipeline reads
them, so the labels that judge Jev here are not the labels that chose the composite weights (decision 0021).

Reported separately, never pooled:
  random            an unbiased read on agreement (stratified by stars, spread across places)
  value_probe       reviews Jev said mention value
  divergence_probe  reviews where an aspect disagreed with the stars: the halo test
Probes were picked using Jev's own output, so they say how Jev does on those reviews, not how it does overall.

The halo test: among reviews where the person says the aspect IS mentioned, regress Jev's score on the person's level and the
star rating. If Jev reads the text, the stars add nothing once the person's level is known (coefficient near 0). If overall tone
leaks into each aspect, the stars coefficient is positive. Intervals come from resampling whole places.
"""

import argparse
import math
from collections import defaultdict

import numpy as np
from scipy.stats import spearmanr

from streetwalker import db
from streetwalker.aspects import ASPECTS, SCORE_TOP
from streetwalker.metrics import cohens_kappa

MENTION = 0.5
BOOT = 500


def load_rows(conn, batch: int = 1) -> list[dict]:
    """One row per labelled item with the person's labels and Jev's answers. Repeat items keep their link to the original."""
    from streetwalker.aspect_labels import latest_labels

    labels = latest_labels(conn, batch)
    cur = conn.cursor()
    items = cur.execute("SELECT i.item_id, i.review_id, i.stratum, i.repeat_of FROM aspect_label_item i WHERE i.batch = %s ORDER BY i.rank", (batch,)).fetchall()
    run = cur.execute("SELECT max(id) FROM aspect_run WHERE finished_at IS NOT NULL AND purpose LIKE 'full%'").fetchone()[0]
    info = {r[0]: r[1:] for r in cur.execute(
        "SELECT r.review_id, r.stars, (SELECT place_id FROM place_review pr WHERE pr.review_id = r.review_id LIMIT 1) FROM yelp_review r "
        "WHERE r.review_id = ANY(%s)", ([i[1] for i in items],)).fetchall()}
    jev: dict[str, dict] = defaultdict(dict)
    for rid, aspect, m, sc, conf in cur.execute(
            "SELECT review_id, aspect, mentioned, score, confidence FROM aspect_score WHERE run_id = %s AND review_id = ANY(%s)", (run, [i[1] for i in items])):
        jev[rid][aspect] = (m, sc, conf)
    rows = []
    for item_id, rid, stratum, repeat_of in items:
        if item_id in labels and rid in info and rid in jev:
            rows.append({"item_id": item_id, "review_id": rid, "stratum": stratum, "repeat_of": repeat_of, "stars": info[rid][0],
                         "place_id": info[rid][1], "human": labels[item_id], "jev": jev[rid]})
    return rows


def mention_agreement(rows: list[dict], aspect: str) -> dict:
    h = [r["human"][aspect] is not None for r in rows]
    j = [r["jev"][aspect][0] >= MENTION for r in rows]
    tp, fp = sum(a and b for a, b in zip(h, j, strict=True)), sum((not a) and b for a, b in zip(h, j, strict=True))
    fn = sum(a and (not b) for a, b in zip(h, j, strict=True))
    return {"n": len(rows), "human_rate": sum(h) / len(h) if h else float("nan"), "jev_rate": sum(j) / len(j) if j else float("nan"),
            "precision": tp / (tp + fp) if tp + fp else float("nan"), "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "kappa": cohens_kappa([str(x) for x in h], [str(x) for x in j])}


def level_agreement(rows: list[dict], aspect: str) -> dict:
    """Among reviews both the person and Jev say mention the aspect."""
    both = [r for r in rows if r["human"][aspect] is not None and r["jev"][aspect][0] >= MENTION]
    if len(both) < 3:
        return {"n": len(both)}
    h = np.array([r["human"][aspect] for r in both], float)
    j = np.array([r["jev"][aspect][1] for r in both], float)
    return {"n": len(both), "exact": float((np.rint(j) == h).mean()), "within1": float((np.abs(j - h) <= 1).mean()), "mae": float(np.abs(j - h).mean()),
            "bias": float((j - h).mean()), "rho": float(spearmanr(j, h).correlation) if h.std() > 0 and j.std() > 0 else float("nan")}


def confidence_vs_error(rows: list[dict], aspect: str) -> list[tuple[str, float, int]]:
    both = [r for r in rows if r["human"][aspect] is not None and r["jev"][aspect][0] >= MENTION]
    if len(both) < 9:
        return []
    both.sort(key=lambda r: r["jev"][aspect][2])
    k = len(both) // 3
    thirds = [("least confident", both[:k]), ("middle", both[k : 2 * k]), ("most confident", both[2 * k :])]
    return [(name, float(np.mean([abs(r["jev"][aspect][1] - r["human"][aspect]) for r in part])), len(part)) for name, part in thirds]


def _halo_coefficients(rows: list[dict], aspect: str) -> tuple[float, float] | None:
    both = [r for r in rows if r["human"][aspect] is not None]
    if len(both) < 12:
        return None
    y = np.array([r["jev"][aspect][1] / SCORE_TOP for r in both])
    X = np.column_stack([np.ones(len(both)), [r["human"][aspect] / SCORE_TOP for r in both], [(r["stars"] - 1) / 4 for r in both]])
    if np.linalg.matrix_rank(X) < 3:
        return None
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    return float(coef[1]), float(coef[2])  # weight on the person's level, weight on the stars


def halo(rows: list[dict], aspect: str, seed: int = 0) -> dict | None:
    """Stars coefficient of Jev's score after the person's level, with a place-resampled 95% interval."""
    est = _halo_coefficients(rows, aspect)
    if est is None:
        return None
    by_place: dict = defaultdict(list)
    for r in rows:
        by_place[r["place_id"]].append(r)
    places = sorted(by_place)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(BOOT):
        sample = [r for p in rng.choice(places, len(places)) for r in by_place[p]]
        e = _halo_coefficients(sample, aspect)
        if e is not None:
            draws.append(e[1])
    lo, hi = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))) if draws else (float("nan"), float("nan"))
    return {"human_weight": est[0], "stars_weight": est[1], "stars_lo": lo, "stars_hi": hi, "n": sum(r["human"][aspect] is not None for r in rows)}


def error_correlation(rows: list[dict]) -> dict[tuple[str, str], tuple[float, int]]:
    """Correlation of Jev's error (Jev minus the person) between aspects, where both aspects are mentioned by both. A shared
    per-review error, such as a general positivity bias, shows up as errors that move together. It does NOT detect a halo whose
    errors are independent across aspects; the regression in halo() is the test for that."""
    out = {}
    for i, a in enumerate(ASPECTS):
        for b in ASPECTS[i + 1 :]:
            rs = [r for r in rows if all(r["human"][x] is not None and r["jev"][x][0] >= MENTION for x in (a, b))]
            if len(rs) >= 10:
                ea = [r["jev"][a][1] - r["human"][a] for r in rs]
                eb = [r["jev"][b][1] - r["human"][b] for r in rs]
                out[(a, b)] = (float(np.corrcoef(ea, eb)[0, 1]) if np.std(ea) > 0 and np.std(eb) > 0 else float("nan"), len(rs))
    return out


def consistency(rows: list[dict]) -> dict:
    """The person against themself on the repeated items: the ceiling for any agreement with Jev."""
    by_item = {r["item_id"]: r for r in rows}
    pairs = [(by_item[r["repeat_of"]], r) for r in rows if r["repeat_of"] in by_item]
    out = {"pairs": len(pairs)}
    if not pairs:
        return out
    ment = [(a["human"][x] is not None, b["human"][x] is not None) for a, b in pairs for x in ASPECTS]
    out["mention_agreement"] = float(np.mean([p == q for p, q in ment]))
    lv = [(a["human"][x], b["human"][x]) for a, b in pairs for x in ASPECTS if a["human"][x] is not None and b["human"][x] is not None]
    if lv:
        out["level_pairs"] = len(lv)
        out["exact"] = float(np.mean([p == q for p, q in lv]))
        out["within1"] = float(np.mean([abs(p - q) <= 1 for p, q in lv]))
    return out


def fmt(x: float, spec: str = ".2f") -> str:
    return "  n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def report(rows: list[dict]) -> None:
    print("NOT A RESULT UNTIL BATCH 1 IS COMPLETE AND READ WITH ITS SAMPLE SIZES. Each part below is reported alone.")
    parts = {"random": [r for r in rows if r["stratum"] == "random"], "value_probe": [r for r in rows if r["stratum"] == "value_probe"],
             "divergence_probe": [r for r in rows if r["stratum"] == "divergence_probe"]}
    print("\nlabelled items: " + ", ".join(f"{k} {len(v)}" for k, v in parts.items()) + f", repeats {sum(r['stratum'] == 'repeat' for r in rows)}")
    for name, part in parts.items():
        if not part:
            continue
        print(f"\n===== {name} (n={len(part)}) =====")
        print("Does Jev know whether an aspect is mentioned? (the person's mention rate, Jev's, and Jev's precision, recall and kappa against the person)")
        for a in ASPECTS:
            m = mention_agreement(part, a)
            print(f"  {a:11s} person {fmt(m['human_rate'], '.0%')} Jev {fmt(m['jev_rate'], '.0%')}  precision {fmt(m['precision'])} recall {fmt(m['recall'])} kappa {fmt(m['kappa'])}")
        print("When both say mentioned: does Jev's score match the person's level? (levels 0 to 4)")
        for a in ASPECTS:
            lv = level_agreement(part, a)
            if lv["n"] < 3:
                print(f"  {a:11s} n={lv['n']} (too few)")
                continue
            print(f"  {a:11s} n={lv['n']:3d}  exact {fmt(lv['exact'], '.0%')}  within 1 {fmt(lv['within1'], '.0%')}  mean abs error {fmt(lv['mae'])}  bias {fmt(lv['bias'], '+.2f')}  rho {fmt(lv['rho'])}")
        print("Does Jev's confidence predict its error? (mean abs error in the least, middle and most confident third)")
        for a in ASPECTS:
            c = confidence_vs_error(part, a)
            if c:
                print(f"  {a:11s} " + "  ".join(f"{n}: {e:.2f} (n={k})" for n, e, k in c))
        print("Halo: weight of the STARS on Jev's score after the person's level (0 = Jev reads the text; above 0 = overall tone leaks in)")
        for a in ASPECTS:
            h = halo(part, a)
            if h:
                print(f"  {a:11s} n={h['n']:3d}  person's level {fmt(h['human_weight'])}, stars {fmt(h['stars_weight'], '+.2f')} [{fmt(h['stars_lo'], '+.2f')}, {fmt(h['stars_hi'], '+.2f')}]")
        ec = error_correlation(part)
        if ec:
            print("Do Jev's errors move together across aspects? (positive correlations mean a shared per-review error, e.g. a general positivity bias)")
            print("  " + "  ".join(f"{a}/{b} {fmt(r)} (n={n})" for (a, b), (r, n) in ec.items()))
    c = consistency(rows)
    print(f"\nThe labeller against themself on {c['pairs']} repeated items (the ceiling on agreement with anyone)")
    if c["pairs"]:
        print(f"  mention decisions agree {fmt(c['mention_agreement'], '.0%')}" + (f"; levels exact {fmt(c['exact'], '.0%')}, within 1 {fmt(c['within1'], '.0%')} on {c['level_pairs']} aspect pairs" if "exact" in c else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1)
    args = ap.parse_args()
    with db.connect() as conn:
        rows = load_rows(conn, args.batch)
    if not rows:
        print("no labelled items yet")
        return
    report(rows)


if __name__ == "__main__":
    main()
