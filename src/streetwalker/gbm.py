"""Gradient-boosted baselines on tier-0 evidence features.   Usage: python -m streetwalker.gbm

Protocol (decision 0008): hyperparameters are chosen by street-grouped 5-fold cross-validation over
train + dev combined (log-loss). Every train and dev prediction stored is out-of-fold, so no reported
number is in-sample. Test rows are predicted by a final model fit on all of train + dev. Street names
are not features. Three feature sets mirror the evidence ablation: geometry, + tags, + street/context.
"""

import argparse
import json
import warnings

import numpy as np
import pandas as pd
import psycopg
from joblib import Parallel, delayed
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, log_loss
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits

from streetwalker import db
from streetwalker.calibration import ece
from streetwalker.features import CATEGORICAL, FEATURE_SETS, ROADS, extract
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.metrics import accuracy, binary, macro_f1, multiclass_log_loss, per_class

warnings.filterwarnings("ignore")

SEED = 0
N_FOLDS = 5
FLOOR = 1e-6
GRID = [
    {"learning_rate": lr, "max_iter": it, "max_leaf_nodes": nl, "min_samples_leaf": msl}
    for lr in (0.1, 0.05)
    for it in (30, 60, 120)
    for nl in (4, 7)
    for msl in (10, 40)
]
CATEGORIES = {
    "building_cat": ["yes", "house", "apartments", "residential_other", "commercial", "civic", "industrial",
                     "accessory", "other"],
    "road_class": [*ROADS, "other"],
}
COMMERCIAL_ANY = [D1_CLASSES.index("commercial"), D1_CLASSES.index("mixed-use")]


def load(conn: psycopg.Connection) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT g.building_id, g.split, g.group_key, g.d1_class, g.d3_food, a.slug, e.payload "
        "FROM ground_truth g JOIN evidence e ON e.building_id = g.building_id AND e.tier = 0 "
        "JOIN building b ON b.id = g.building_id JOIN area a ON a.id = b.area_id ORDER BY g.building_id"
    ).fetchall()
    feats = pd.DataFrame([extract(r[6]) for r in rows])
    for col in CATEGORICAL:
        feats[col] = pd.Categorical(feats[col], categories=CATEGORIES[col])
    meta = pd.DataFrame(rows, columns=["building_id", "split", "group_key", "d1", "d3", "area", "payload"]).drop(columns="payload")
    return pd.concat([meta, feats], axis=1)


def make_model(params: dict) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        **params, l2_regularization=1.0, early_stopping=False,
        categorical_features="from_dtype", random_state=SEED,
    )


def full_proba(model: HistGradientBoostingClassifier, X: pd.DataFrame, classes: tuple[str, ...]) -> np.ndarray:
    """Probabilities in a fixed class order; classes unseen in training get a small floor."""
    p = np.full((len(X), len(classes)), FLOOR)
    for j, c in enumerate(model.classes_):
        p[:, classes.index(c)] = model.predict_proba(X)[:, j]
    return p / p.sum(axis=1, keepdims=True)


def _fit_fold(X, y, tr, va, params, classes):
    with threadpool_limits(limits=2):
        m = make_model(params).fit(X.iloc[tr], y[tr])
        return va, full_proba(m, X.iloc[va], classes)


def cross_validate(X: pd.DataFrame, y: np.ndarray, folds: list, classes: tuple[str, ...], params: dict) -> np.ndarray:
    """Out-of-fold probabilities for every row."""
    out = np.zeros((len(X), len(classes)))
    for va, p in Parallel(n_jobs=4)(delayed(_fit_fold)(X, y, tr, va, params, classes) for tr, va in folds):
        out[va] = p
    return out


def choose(X, y, folds, classes, label: str):
    best = None
    for params in GRID:
        oof = cross_validate(X, y, folds, classes, params)
        ll = multiclass_log_loss(list(y), oof.tolist(), classes)
        print(f"    {label} {params}  log-loss {ll:.4f}", flush=True)
        if best is None or ll < best[0]:
            best = (ll, params, oof)
    return best


def permutation_importance(X, y, folds, classes, params, n_repeats=3):
    """Mean increase in held-out log-loss when one feature is shuffled, averaged over folds."""
    rng = np.random.default_rng(SEED)
    gains = dict.fromkeys(X.columns, 0.0)
    for tr, va in folds:
        with threadpool_limits(limits=4):
            m = make_model(params).fit(X.iloc[tr], y[tr])
            Xv, yv = X.iloc[va].copy(), y[va]
            base = multiclass_log_loss(list(yv), full_proba(m, Xv, classes).tolist(), classes)
            for col in X.columns:
                orig = Xv[col].copy()
                for _ in range(n_repeats):
                    Xv[col] = orig.sample(frac=1.0, random_state=int(rng.integers(1 << 30))).to_numpy()
                    shuffled = multiclass_log_loss(list(yv), full_proba(m, Xv, classes).tolist(), classes)
                    gains[col] += (shuffled - base) / (n_repeats * len(folds))
                Xv[col] = orig
    return sorted(gains.items(), key=lambda kv: -kv[1])


def best_threshold(truth: np.ndarray, score: np.ndarray) -> float:
    grid = np.arange(0.05, 0.95, 0.01)
    f1s = [binary(list(truth), list(score >= t)).f1 for t in grid]
    return float(grid[int(np.argmax(f1s))])


def report_oof(name: str, df: pd.DataFrame, oof: np.ndarray, d3_oof: np.ndarray, d3_tau: float) -> None:
    classes = list(D1_CLASSES)
    pred = [classes[i] for i in oof.argmax(axis=1)]
    for split in ("train", "dev"):
        m = (df["split"] == split).to_numpy()
        truth = list(df["d1"][m])
        pr = [p for p, keep in zip(pred, m, strict=True) if keep]
        stats = per_class(truth, pr, classes)
        ca = binary([t in ("commercial", "mixed-use") for t in truth], [p in ("commercial", "mixed-use") for p in pr])
        score = oof[m][:, COMMERCIAL_ANY].sum(axis=1)
        ap = average_precision_score([t in ("commercial", "mixed-use") for t in truth], score)
        conf = list(oof[m].max(axis=1))
        correct = [t == p for t, p in zip(truth, pr, strict=True)]
        f = binary(list(df["d3"][m]), list(d3_oof[m] >= d3_tau))
        print(f"  {name:13s} {split:5s} n={m.sum():4d} acc {accuracy(truth, pr):.3f} macroF1 {macro_f1(stats):.3f} | "
              f"comm-any P {ca.precision:.2f} R {ca.recall:.2f} F1 {ca.f1:.2f} AP {ap:.2f} | "
              f"D3 P {f.precision:.2f} R {f.recall:.2f} F1 {f.f1:.2f} | ECE {ece(conf, correct):.3f}")


def store(conn: psycopg.Connection, name: str, ids, d1_probs: np.ndarray, d3_probs: np.ndarray, d3_tau: float) -> None:
    classes = list(D1_CLASSES)
    rows = []
    for bid, p, f in zip(ids, d1_probs, d3_probs, strict=True):
        probs = {c: round(float(p[i]), 5) for i, c in enumerate(classes)} | {"food": round(float(f), 5)}
        rows.append((int(bid), name, classes[int(p.argmax())], None, bool(f >= d3_tau), "gbm", json.dumps(probs), float(p.max())))
    conn.execute("DELETE FROM baseline_prediction WHERE baseline = %s", (name,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO baseline_prediction (building_id, baseline, d1_class, d2_type, d3_food, rule, probs, confidence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            rows,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=list(FEATURE_SETS), choices=list(FEATURE_SETS))
    args = ap.parse_args()

    with db.connect() as conn:
        db.migrate(conn)
        df = load(conn)
        classes = D1_CLASSES
        tv = (df["split"] != "test").to_numpy()
        te = ~tv
        y = df["d1"].to_numpy()
        y3 = df["d3"].to_numpy().astype(int)
        folds = list(StratifiedGroupKFold(N_FOLDS, shuffle=True, random_state=SEED).split(
            np.zeros(tv.sum()), y[tv], df["group_key"][tv]))
        print(f"train+dev {tv.sum()} buildings in {df['group_key'][tv].nunique()} street groups; test {te.sum()} held out\n")

        summary = []
        for fs in args.sets:
            cols = FEATURE_SETS[fs]
            X = df[cols]
            Xtv = X[tv].reset_index(drop=True)
            print(f"== gbm-{fs}: {len(cols)} features", flush=True)
            ll, params, oof = choose(Xtv, y[tv], folds, classes, "D1")

            # D3 (food-serving): binary model, decision threshold tuned on out-of-fold F1
            d3_best = None
            for p3 in GRID:
                oof3 = np.zeros(tv.sum())
                for tr, va in folds:
                    with threadpool_limits(limits=4):
                        m = make_model(p3).fit(Xtv.iloc[tr], y3[tv][tr])
                        oof3[va] = m.predict_proba(Xtv.iloc[va])[:, 1]
                l3 = log_loss(y3[tv], oof3)
                if d3_best is None or l3 < d3_best[0]:
                    d3_best = (l3, p3, oof3)
            _, p3, oof3 = d3_best
            tau = best_threshold(y3[tv], oof3)
            print(f"    chosen D1 {params} (log-loss {ll:.4f}); D3 {p3}, threshold {tau:.2f}", flush=True)

            # final models on all of train + dev predict the test rows
            with threadpool_limits(limits=8):
                final1 = make_model(params).fit(Xtv, y[tv])
                final3 = make_model(p3).fit(Xtv, y3[tv])
                test_d1 = full_proba(final1, X[te], classes)
                test_d3 = final3.predict_proba(X[te])[:, 1]

            ids = df["building_id"].to_numpy()
            d1_all = np.zeros((len(df), len(classes)))
            d3_all = np.zeros(len(df))
            d1_all[tv], d1_all[te] = oof, test_d1
            d3_all[tv], d3_all[te] = oof3, test_d3
            store(conn, f"gbm-{fs}", ids, d1_all, d3_all, tau)
            conn.commit()
            report_oof(f"gbm-{fs}", df[tv].reset_index(drop=True), oof, oof3, tau)
            summary.append((fs, params, p3, tau))
            if fs == "full":
                print("  permutation importance on held-out folds (increase in log-loss):")
                for name, g in permutation_importance(Xtv, y[tv], folds, classes, params)[:14]:
                    print(f"    {name:22s} {g:+.4f}")
            print(flush=True)
        print("params:", json.dumps({fs: {"d1": p, "d3": p3, "d3_threshold": t} for fs, p, p3, t in summary}))


if __name__ == "__main__":
    main()
