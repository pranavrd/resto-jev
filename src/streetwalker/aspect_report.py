"""Sanity report for aspect scoring (decision 0020).   Usage: .venv/bin/python -m streetwalker.aspect_report [--run ID]

PRIVATE: prints figures derived from Yelp Data; keep the output out of git (docs/private/). There are no human labels yet, so
this checks that the scores behave sensibly (they are not accuracy): mention rates, agreement with the star rating, whether
confidence carries information, and how often an aspect disagrees with the overall stars.
"""

import argparse

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from streetwalker import db
from streetwalker.aspects import ASPECTS, SCORE_TOP

MENTION = 0.5
MIN_MENTIONS = 10  # a place needs this many mentions of an aspect for a place-level mean to be worth showing


def load(conn, run_id: int) -> pd.DataFrame:
    cur = conn.execute(
        """
        SELECT s.review_id, s.aspect, s.mentioned, s.score, s.confidence, r.stars, extract(year FROM r.date)::int AS year,
               pr.place_id, a.slug AS area, y.stars AS biz_stars
        FROM aspect_score s JOIN yelp_review r USING (review_id)
        JOIN (SELECT DISTINCT ON (review_id) review_id, place_id FROM place_review ORDER BY review_id, place_id) pr USING (review_id)
        JOIN place p ON p.id = pr.place_id JOIN area a ON a.id = p.area_id JOIN yelp_business y ON y.business_id = r.business_id
        WHERE s.run_id = %s
        """,
        (run_id,),
    )
    return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def report(df: pd.DataFrame) -> None:
    n_rev = df["review_id"].nunique()
    print(f"{n_rev:,} reviews, {df['place_id'].nunique()} places")
    df = df.assign(men=df["mentioned"] >= MENTION)

    print("\nMention rate (probability of mention at least 0.5)")
    print(f"  {'aspect':11s} {'all':>6s} " + " ".join(f"{s}*" .rjust(6) for s in (1, 2, 3, 4, 5)) + "   " + " ".join(f"{a[:8]:>13s}" for a in sorted(df['area'].unique())))
    for a in ASPECTS:
        d = df[df["aspect"] == a]
        print(f"  {a:11s} {d['men'].mean():6.0%} " + " ".join(f"{d[d['stars'] == s]['men'].mean():6.0%}" for s in (1, 2, 3, 4, 5)) + "   "
              + " ".join(f"{d[d['area'] == ar]['men'].mean():13.0%}" for ar in sorted(df['area'].unique())))
    print(f"  mention probability is decisive (below 0.1 or above 0.9) for {((df['mentioned'] < .1) | (df['mentioned'] > .9)).mean():.0%} of answers")

    print("\nSentiment among reviews that mention the aspect: mean score (0 clearly negative to 4 clearly positive) by the review's stars")
    print(f"  {'aspect':11s} {'n':>6s} {'rho vs stars':>13s} " + " ".join(f"{s}*".rjust(6) for s in (1, 2, 3, 4, 5)) + "   not mentioned: mean score")
    for a in ASPECTS:
        d = df[(df["aspect"] == a) & df["men"]]
        rho = spearmanr(d["score"], d["stars"]).correlation
        off = df[(df["aspect"] == a) & ~df["men"]]["score"].mean()
        print(f"  {a:11s} {len(d):6d} {rho:13.2f} " + " ".join(f"{d[d['stars'] == s]['score'].mean():6.2f}" for s in (1, 2, 3, 4, 5)) + f"   {off:.2f}")

    print("\nDoes confidence carry information? Mean gap between the aspect score and the review's own stars (both on 0 to 1), by confidence")
    for a in ASPECTS:
        d = df[(df["aspect"] == a) & df["men"]].copy()
        d["gap"] = (d["score"] / SCORE_TOP - (d["stars"] - 1) / 4).abs()
        d["band"] = pd.qcut(d["confidence"].rank(method="first"), 3, labels=["low", "mid", "high"])  # rank first: many answers sit at exactly 1.0
        print(f"  {a:11s} " + "  ".join(f"{b}: {g:.2f} (n={n})" for b, g, n in d.groupby("band", observed=True).agg(g=("gap", "mean"), n=("gap", "size")).reset_index().itertuples(index=False)))

    print("\nWhere an aspect disagrees with the overall stars (reviews that mention it)")
    for a in ASPECTS:
        d = df[(df["aspect"] == a) & df["men"]]
        hi, lo = d[d["stars"] >= 4], d[d["stars"] <= 2]
        print(f"  {a:11s} 4-5 star reviews with a negative {a} (score <= 1.5): {(hi['score'] <= 1.5).mean():5.1%} of {len(hi)};   "
              f"1-2 star reviews with a positive {a} (score >= 2.5): {(lo['score'] >= 2.5).mean():5.1%} of {len(lo)}")

    print(f"\nPlace level (places with at least {MIN_MENTIONS} mentions): mean sentiment among mentions")
    for a in ASPECTS:
        d = df[(df["aspect"] == a) & df["men"]]
        g = d.groupby("place_id").agg(n=("score", "size"), mean=("score", "mean"), biz=("biz_stars", "first")).query("n >= @MIN_MENTIONS")
        if len(g) > 5:
            print(f"  {a:11s} {len(g):3d} places, spread of place means {g['mean'].min():.2f} to {g['mean'].max():.2f} (sd {g['mean'].std():.2f}); "
                  f"rho with Yelp's business stars {spearmanr(g['mean'], g['biz']).correlation:.2f}")
    wide = df[df["men"]].pivot_table(index=["place_id"], columns="aspect", values="score", aggfunc="mean")
    print("  correlation between aspects across places (do they differ, or is it one 'good restaurant' score?)")
    print(wide.corr(method="spearman").round(2).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int)
    args = ap.parse_args()
    with db.connect() as conn:
        run_id = args.run or conn.execute("SELECT max(id) FROM aspect_run WHERE finished_at IS NOT NULL AND purpose LIKE 'full%'").fetchone()[0]
        info = conn.execute("SELECT purpose, prompt_version, model_version, n_reviews, input_tokens, est_cost_usd FROM aspect_run WHERE id = %s", (run_id,)).fetchone()
        errs = conn.execute("SELECT count(*) FROM aspect_request WHERE run_id = %s AND error IS NOT NULL", (run_id,)).fetchone()[0]
        print(f"run {run_id}: {info[0]}, prompt {info[1]}, {info[2]}, {info[3]:,} reviews, {info[4]:,} input tokens, est. ${info[5]:.2f}, {errs} errors")
        report(load(conn, run_id))


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
