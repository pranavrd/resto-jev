"""Tier-0 stackers: models that take Jev's answers as inputs.   Usage: python -m streetwalker.stacker

  stack-gbm  boosted trees over the evidence features plus Jev's D1 distribution, confidence, D3 and D2
  stack-lr   a small logistic recalibration of Jev alone (its log-probabilities, food probability and a
             silent-building flag): can Jev's own numbers be made honest without any other evidence?

Same protocol as gbm.py (decision 0008): street-grouped 5-fold CV over train + dev picks the settings,
every train and dev prediction is out-of-fold, test comes from a final model. Jev needs no training, so
nothing about Jev is fitted on the folds; only the stacker is.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from streetwalker import db
from streetwalker.features import FEATURE_SETS, JEV_CLASSES
from streetwalker.gbm import best_threshold, fit_set, full_proba, prepare, report_oof, store
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.metrics import multiclass_log_loss

C_GRID = (0.01, 0.1, 1.0, 10.0)


def lr_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Jev's log-probabilities, its food logit and a flag for buildings with no tag, POI or name."""
    x = pd.DataFrame({f"log_p_{c}": np.log(df[f"jev_p_{c}"].clip(1e-4, 1.0)) for c in JEV_CLASSES})
    p = df["jev_p_food"].clip(1e-3, 1 - 1e-3)
    x["food_logit"] = np.log(p / (1 - p))
    x["silent"] = ((df["n_pois"] == 0) & (df["has_use_tag"] == 0) & (df["has_name"] == 0)).astype(float)
    x["silent_x_comm"] = x["silent"] * x["log_p_commercial"]
    return x


def fit_lr(conn, df, folds, tv, te, name: str = "stack-lr") -> None:
    classes = D1_CLASSES
    y = df["d1"].to_numpy()
    y3 = df["d3"].to_numpy().astype(int)
    X = lr_matrix(df)
    Xtv = X[tv].reset_index(drop=True)
    print(f"== {name}: {X.shape[1]} features", flush=True)

    def model(c):
        return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=3000))

    best = None
    for c in C_GRID:
        oof = np.zeros((tv.sum(), len(classes)))
        for tr, va in folds:
            m = model(c).fit(Xtv.iloc[tr], y[tv][tr])
            oof[va] = full_proba(m, Xtv.iloc[va], classes)
        ll = multiclass_log_loss(list(y[tv]), oof.tolist(), classes)
        print(f"    D1 C={c}  log-loss {ll:.4f}", flush=True)
        if best is None or ll < best[0]:
            best = (ll, c, oof)
    ll, c, oof = best

    d3_best = None
    Xd3 = np.c_[X["food_logit"], X["silent"], df["has_food"]][tv]
    for c3 in C_GRID:
        oof3 = np.zeros(tv.sum())
        for tr, va in folds:
            m = model(c3).fit(Xd3[tr], y3[tv][tr])
            oof3[va] = m.predict_proba(Xd3[va])[:, 1]
        l3 = log_loss(y3[tv], oof3)
        if d3_best is None or l3 < d3_best[0]:
            d3_best = (l3, c3, oof3)
    _, c3, oof3 = d3_best
    tau = best_threshold(y3[tv], oof3)
    print(f"    chosen D1 C={c} (log-loss {ll:.4f}); D3 C={c3}, threshold {tau:.2f}", flush=True)

    final1 = model(c).fit(Xtv, y[tv])
    final3 = model(c3).fit(Xd3, y3[tv])
    d1_all = np.zeros((len(df), len(classes)))
    d3_all = np.zeros(len(df))
    d1_all[tv], d1_all[te] = oof, full_proba(final1, X[te], classes)
    d3_all[tv], d3_all[te] = oof3, final3.predict_proba(np.c_[X["food_logit"], X["silent"], df["has_food"]][te])[:, 1]
    store(conn, name, df["building_id"].to_numpy(), d1_all, d3_all, tau)
    conn.commit()
    report_oof(name, df[tv].reset_index(drop=True), oof, oof3, tau)
    print(flush=True)


def main() -> None:
    with db.connect() as conn:
        db.migrate(conn)
        df, tv, te, folds = prepare(conn, with_jev=True)
        fit_lr(conn, df, folds, tv, te)
        fit_set(conn, df, folds, tv, te, "stack-gbm", FEATURE_SETS["stack"], importance=True)


if __name__ == "__main__":
    main()
