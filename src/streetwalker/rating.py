"""Provisional restaurant ratings from aspect scores (decision 0021).   Usage: .venv/bin/python -m streetwalker.rating [--table]

PROVISIONAL, EVERYWHERE IT APPEARS. The aspect scores behind this have not been checked against human labels, so nothing
here is a result: not a ranking, not an aspect claim. Every table row carries status = 'provisional' (enforced by a CHECK)
and every printout starts with the same banner.

PRIVATE: derived from Yelp Data (agreement 4A, 4E, 5). Output stays out of git (docs/private/).

The method, per place and aspect:
  - each review that mentions the aspect contributes its score (0 to 4, divided by 4) with weight
    mention probability x recency weight, where recency halves every HALF_LIFE_YEARS before the snapshot's last review;
  - the weighted scores become a Beta posterior on the place's true level (0 to 1) around a prior set from all places, with the
    prior's strength estimated from how much places really differ (empirical Bayes, no labels involved), so a place with few
    mentions is pulled toward the average and a place with many is not;
  - the effective sample size (Kish) scales the pseudo-counts, so recency weighting does not make a place look better known
    than it is;
  - the four aspects are combined with the FROZEN weights below, by drawing from each posterior, which gives a credible
    interval for the composite and an interval for the rank, not just a rank.

THE COMPOSITE WEIGHTS ARE NOT TUNED ON HUMAN LABELS. They were fixed here before any label existed (weights version w1) and this
module never reads the label tables (a test enforces it). Batch 1 of the labels is the judging set; if weights are ever tuned,
use batches 2 and up, so the labels that choose the weights are not the ones that judge them.
"""

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.stats import beta as beta_dist
from scipy.stats import spearmanr

from streetwalker import db
from streetwalker.aspects import ASPECTS, SCORE_TOP

BANNER = ("PROVISIONAL: the aspect scores behind this are not yet validated against human labels (decision 0021). "
          "Do not quote any ranking or aspect figure from this as a result.")

WEIGHTS_VERSION = "w1"
# Fixed a priori, before any label existed. Food is why a restaurant exists, so it counts most; service and atmosphere shape the
# visit; value is the most personal and the aspect Jev is least sure about, so it counts least. Sensitivity to these choices is
# reported (SENSITIVITY), never optimised against labels.
WEIGHTS = {"food": 0.40, "service": 0.25, "atmosphere": 0.20, "value": 0.15}
HALF_LIFE_YEARS = 3.0
SENSITIVITY = {
    "equal weights": {"weights": {a: 0.25 for a in ASPECTS}},
    "food-heavy (0.6/0.2/0.1/0.1)": {"weights": {"food": 0.6, "service": 0.2, "atmosphere": 0.1, "value": 0.1}},
    "value-heavy (0.25/0.2/0.2/0.35)": {"weights": {"food": 0.25, "service": 0.2, "atmosphere": 0.2, "value": 0.35}},
    "half-life 1.5 years": {"half_life": 1.5},
    "no recency weighting": {"half_life": None},
    "prior half as strong": {"kappa_scale": 0.5},
    "prior twice as strong": {"kappa_scale": 2.0},
}
KAPPA_RANGE = (2.0, 200.0)  # prior strength in pseudo-reviews, clipped
MIN_EFF_FOR_PRIOR = 5.0  # only places this well observed inform the prior's strength
DRAWS = 4000
SEED = 20261005
CI = (0.025, 0.975)


def recency_weight(age_years: float, half_life: float | None) -> float:
    return 1.0 if half_life is None else 0.5 ** (max(age_years, 0.0) / half_life)


@dataclass(frozen=True)
class Stats:
    """A place's weighted evidence about one aspect."""

    total_weight: float
    n_eff: float
    mean: float  # weighted mean of the scores on 0 to 1 (nan when there is no evidence)
    alpha: float  # pseudo-counts after scaling the weights down to the effective sample size
    beta: float
    var: float  # weighted variance of the scores


def place_stats(obs: list[tuple[float, float]]) -> Stats:
    """obs: (score on 0 to 1, weight). The weight is mention probability x recency weight."""
    w = np.array([o[1] for o in obs], dtype=float)
    x = np.array([o[0] for o in obs], dtype=float)
    total = float(w.sum())
    if total <= 0:
        return Stats(0.0, 0.0, float("nan"), 0.0, 0.0, 0.0)
    n_eff = total**2 / float((w**2).sum())  # Kish: equal weights give n, uneven weights give less
    scale = n_eff / total
    mean = float((w * x).sum() / total)
    return Stats(total, n_eff, mean, scale * float((w * x).sum()), scale * float((w * (1 - x)).sum()), float((w * (x - mean) ** 2).sum() / total))


def estimate_kappa(stats: list[Stats], mu0: float) -> float:
    """Prior strength in pseudo-reviews by the method of moments: how much do place means differ beyond what sampling noise
    explains? Beta(k mu, k (1 - mu)) has variance mu (1 - mu) / (k + 1), so k = mu (1 - mu) / V_between - 1."""
    good = [s for s in stats if s.n_eff >= MIN_EFF_FOR_PRIOR]
    if len(good) < 5:
        return KAPPA_RANGE[1] / 4
    means = np.array([s.mean for s in good])
    noise = float(np.mean([s.var / s.n_eff for s in good]))
    between = max(float(means.var()) - noise, 1e-4)
    return float(np.clip(mu0 * (1 - mu0) / between - 1, *KAPPA_RANGE))


def posterior(s: Stats, mu0: float, kappa: float) -> tuple[float, float, float, float, float]:
    """(mean, ci_low, ci_high, alpha, beta) of the Beta posterior on the place's level."""
    a, b = kappa * mu0 + s.alpha, kappa * (1 - mu0) + s.beta
    return a / (a + b), float(beta_dist.ppf(CI[0], a, b)), float(beta_dist.ppf(CI[1], a, b)), a, b


def composite_draws(posts: dict[str, tuple[float, float]], weights: dict[str, float], rng: np.random.Generator, n: int = DRAWS) -> np.ndarray:
    """Draws of the weighted composite from independent Beta posteriors, one per aspect. posts: aspect -> (alpha, beta)."""
    return sum(weights[a] * rng.beta(*posts[a], size=n) for a in weights)


def rank_intervals(draws: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """draws: places x draws. Rank 1 is best. Returns the rank from the posterior means and the 5th and 95th percentile rank."""
    order_each_draw = (-draws).argsort(axis=0).argsort(axis=0) + 1  # rank of every place within each draw
    mean_rank = (-draws.mean(axis=1)).argsort().argsort() + 1
    return mean_rank, np.percentile(order_each_draw, 5, axis=1).astype(int), np.percentile(order_each_draw, 95, axis=1).astype(int)


@dataclass(frozen=True)
class Params:
    weights: dict[str, float]
    half_life: float | None
    kappa_scale: float = 1.0


DEFAULT = Params(WEIGHTS, HALF_LIFE_YEARS)


def fit(reviews: list[dict], params: Params, seed: int = SEED) -> dict:
    """reviews: dicts with place_id, stars, age_years and aspects {name: (mention probability, score 0 to 4)}.
    Returns per-place aspect posteriors, composite and rank intervals, and the shrunk review stars."""
    by_place: dict[int, list[dict]] = defaultdict(list)
    for r in reviews:
        by_place[r["place_id"]].append(r)
    places = sorted(by_place)
    kappas: dict[str, float] = {}
    mus: dict[str, float] = {}
    stats: dict[str, dict[int, Stats]] = {}
    for a in (*ASPECTS, "stars"):
        stats[a] = {}
        for p in places:
            obs = []
            for r in by_place[p]:
                w = recency_weight(r["age_years"], params.half_life)
                if a == "stars":
                    obs.append(((r["stars"] - 1) / 4, w))
                else:
                    m, s = r["aspects"][a]
                    obs.append((s / SCORE_TOP, m * w))
            stats[a][p] = place_stats(obs)
        pooled = [s for s in stats[a].values() if s.total_weight > 0]
        mus[a] = sum(s.mean * s.total_weight for s in pooled) / sum(s.total_weight for s in pooled)
        kappas[a] = float(np.clip(estimate_kappa(pooled, mus[a]) * params.kappa_scale, *KAPPA_RANGE))
    rng = np.random.default_rng(seed)
    out = {"places": places, "kappa": kappas, "mu": mus, "aspect": {}, "composite": {}, "stars": {}}
    draws = []
    for p in places:
        posts = {a: posterior(stats[a][p], mus[a], kappas[a]) for a in ASPECTS}
        out["aspect"][p] = {a: {"mean": v[0], "lo": v[1], "hi": v[2], "n_mentions": float(sum(m for m, _ in (r["aspects"][a] for r in by_place[p]))),
                                "n_eff": stats[a][p].n_eff} for a, v in posts.items()}
        d = composite_draws({a: (v[3], v[4]) for a, v in posts.items()}, params.weights, rng)
        draws.append(d)
        sp = posterior(stats["stars"][p], mus["stars"], kappas["stars"])
        out["stars"][p] = 1 + 4 * sp[0]
    draws_arr = np.array(draws)
    rank, lo, hi = rank_intervals(draws_arr)
    for i, p in enumerate(places):
        out["composite"][p] = {"mean": 1 + 4 * float(draws_arr[i].mean()), "lo": 1 + 4 * float(np.quantile(draws_arr[i], CI[0])),
                               "hi": 1 + 4 * float(np.quantile(draws_arr[i], CI[1])), "rank": int(rank[i]), "rank_lo": int(lo[i]), "rank_hi": int(hi[i]),
                               "n_reviews": len(by_place[p])}
    return out


def load_reviews(conn, aspect_run_id: int) -> list[dict]:
    cur = conn.cursor()
    snapshot = cur.execute("SELECT max(date) FROM yelp_review").fetchone()[0]
    rows = cur.execute(
        """
        SELECT s.review_id, pr.place_id, r.stars, r.date, s.aspect, s.mentioned, s.score
        FROM aspect_score s JOIN yelp_review r USING (review_id)
        JOIN (SELECT DISTINCT ON (review_id) review_id, place_id FROM place_review ORDER BY review_id, place_id) pr USING (review_id)
        WHERE s.run_id = %s
        """,
        (aspect_run_id,),
    ).fetchall()
    by: dict[str, dict] = {}
    for rid, pid, stars, d, aspect, m, sc in rows:
        r = by.setdefault(rid, {"place_id": pid, "stars": stars, "age_years": (snapshot - d).days / 365.25, "aspects": {}})
        r["aspects"][aspect] = (m, sc)
    return [r for r in by.values() if len(r["aspects"]) == len(ASPECTS)]


def store(conn, aspect_run_id: int, result: dict, params: Params, yelp_stars: dict[int, float]) -> int:
    run_id = conn.execute(
        "INSERT INTO rating_run (aspect_run_id, weights_version, params) VALUES (%s, %s, %s::jsonb) RETURNING id",
        (aspect_run_id, WEIGHTS_VERSION, json.dumps({"weights": params.weights, "half_life_years": params.half_life, "kappa": result["kappa"], "mu": result["mu"]})),
    ).fetchone()[0]
    for p in result["places"]:
        for a, v in result["aspect"][p].items():
            conn.execute("INSERT INTO restaurant_aspect (run_id, place_id, aspect, mean, ci_low, ci_high, n_mentions, n_eff) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (run_id, p, a, v["mean"], v["lo"], v["hi"], v["n_mentions"], v["n_eff"]))
        c = result["composite"][p]
        conn.execute("INSERT INTO restaurant_rating (run_id, place_id, composite, ci_low, ci_high, rank, rank_low, rank_high, stars_shrunk, yelp_stars, n_reviews) "
                     "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                     (run_id, p, c["mean"], c["lo"], c["hi"], c["rank"], c["rank_lo"], c["rank_hi"], result["stars"][p], yelp_stars.get(p), c["n_reviews"]))
    return run_id


def sensitivity(reviews: list[dict], base: dict) -> list[tuple[str, float]]:
    """Spearman correlation of the default ranking with the ranking under each alternative choice."""
    out = []
    places = base["places"]
    ref = [base["composite"][p]["mean"] for p in places]
    for name, change in SENSITIVITY.items():
        params = Params(change.get("weights", WEIGHTS), change.get("half_life", HALF_LIFE_YEARS), change.get("kappa_scale", 1.0))
        alt = fit(reviews, params)
        out.append((name, float(spearmanr(ref, [alt["composite"][p]["mean"] for p in places]).correlation)))
    return out


def print_summary(conn, result: dict, reviews: list[dict], table: bool) -> None:
    print("=" * 110)
    print(BANNER)
    print("=" * 110)
    comp = result["composite"]
    print(f"weights {WEIGHTS_VERSION} {WEIGHTS} (frozen, not tuned on labels); recency half-life {HALF_LIFE_YEARS} years; {len(result['places'])} places, {len(reviews):,} reviews")
    print("prior strength in pseudo-reviews (estimated from how much places differ): " + ", ".join(f"{a} {k:.0f}" for a, k in result["kappa"].items()))
    width = [c["hi"] - c["lo"] for c in comp.values()]
    rw = [c["rank_hi"] - c["rank_lo"] for c in comp.values()]
    print(f"composite 95% interval width on the 1 to 5 scale: median {np.median(width):.2f}, widest {max(width):.2f}")
    print(f"90% rank interval width (of {len(comp)} places): median {int(np.median(rw))}, widest {max(rw)}; a place is distinguishable from its neighbours only when intervals do not overlap")
    stars_gap = [(comp[p]["mean"] - result["stars"][p]) for p in result["places"]]
    print(f"composite minus shrunk review stars: mean {np.mean(stars_gap):+.2f}, spread (sd) {np.std(stars_gap):.2f}; "
          f"rank agreement with the stars alone (Spearman) {spearmanr([comp[p]['mean'] for p in result['places']], [result['stars'][p] for p in result['places']]).correlation:.2f}")
    print("\nHow much do the choices matter? Spearman correlation of the ranking with the default ranking, under each alternative")
    for name, rho in sensitivity(reviews, result):
        print(f"  {name:36s} {rho:.3f}")
    if table:
        names = dict(conn.execute("SELECT id, coalesce(name, address) FROM place").fetchall())
        print("\nPROVISIONAL ranking (a table of provisional numbers is not a result)")
        print(f"  {'rank':>4s} {'90% rank':>9s} {'composite':>10s} {'95% interval':>14s} {'n':>5s}  place")
        for p in sorted(result["places"], key=lambda p: comp[p]["rank"]):
            c = comp[p]
            print(f"  {c['rank']:4d} {c['rank_lo']:3d}-{c['rank_hi']:<4d} {c['mean']:10.2f} {c['lo']:6.2f}-{c['hi']:<6.2f} {c['n_reviews']:5d}  {names[p]}")
    print("\n" + BANNER)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true", help="also print the provisional ranking")
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        run_id = conn.execute("SELECT max(id) FROM aspect_run WHERE finished_at IS NOT NULL AND purpose LIKE 'full%'").fetchone()[0]
        reviews = load_reviews(conn, run_id)
        result = fit(reviews, DEFAULT)
        if not args.no_store:
            ystars = {pid: s for pid, s in conn.execute("SELECT l.place_id, y.stars FROM yelp_link_usable l JOIN yelp_business y USING (business_id)").fetchall()}
            rid = store(conn, run_id, result, DEFAULT, ystars)
            conn.commit()
            print(f"stored provisional rating run {rid} (aspect run {run_id})")
        print_summary(conn, result, reviews, args.table)


if __name__ == "__main__":
    main()
