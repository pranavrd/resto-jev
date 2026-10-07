"""How reliable is a place's aspect score? Split-half reliability and the intraclass correlation (decision 0034).
Usage: .venv/bin/python -m streetwalker.aspect_split_half [--write]

PRIVATE results: reads Yelp-derived scores (aspect_score, place_review), writes only to docs/private/aspect-split-half.md (gitignored).

No human labels, so this is reliability, not validity: it asks whether two independent halves of the same place's reviews give the same
score. If they do not, the score is mostly noise for that place, whatever the scorer's accuracy on a single review. If they do, the score
is at least a consistent property of the place's reviews, which is a necessary condition for it to mean anything and no proof that it does.

For every aspect and for the composite (frozen weights w1, decision 0021), over the places with at least `min_n` reviews that mention the aspect:
  split-half r   reviews randomly halved, each half averaged, Pearson r across places, 200 random splits; the Spearman-Brown step-up
                 2r / (1 + r) estimates the reliability of the full-sample mean
  ICC(1)         share of the variance of single review scores that lies between places (one-way random effects); how much of one review's
                 score says something about the place. With it, the number of mentions needed for a reliability of 0.7 or 0.8
  quartile       the chat shows "in the top quarter" and so on, so: how often a place lands in the same quartile of the places in both halves
Yelp's star rating is put through the same treatment as the benchmark everyone already uses.
"""

import argparse
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

from streetwalker.aspects import ASPECTS
from streetwalker.rating import WEIGHTS

MENTION = 0.5
SPLITS = 200
SEED = 20261007
MIN_NS = (5, 10, 20)
REPORT = Path(__file__).resolve().parents[2] / "docs" / "private" / "aspect-split-half.md"


# ---- the statistics (pure) ------------------------------------------------------------------------------------------------------------

def spearman_brown(r: float, k: float = 2.0) -> float:
    """The reliability of a score built from k times as many reviews as one half, given the correlation r between two halves."""
    return k * r / (1 + (k - 1) * r) if r > -1 / (k - 1) else float("nan")


def pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def halves(values: list[float], rng: random.Random) -> tuple[list[float], list[float]]:
    v = values[:]
    rng.shuffle(v)
    h = len(v) // 2
    return v[:h], v[h:2 * h]  # an odd one out is left out, so both halves have the same size


def quartile_index(scores: dict[str, float]) -> dict[str, int]:
    """0 to 3: which quarter of the places a place's score falls in (3 is the top)."""
    ids = sorted(scores, key=lambda k: scores[k])
    n = len(ids)
    return {k: min(3, 4 * i // n) for i, k in enumerate(ids)}


def split_half(groups: dict[str, list[float]], rng: random.Random, n_splits: int = SPLITS) -> dict:
    """Mean over random splits of the half-to-half correlation, its Spearman-Brown step-up and the quartile agreement. Groups need at least 4 values."""
    ids = [k for k, v in groups.items() if len(v) >= 4]
    rs, agree, near = [], [], []
    for _ in range(n_splits):
        a, b = {}, {}
        for k in ids:
            x, y = halves(groups[k], rng)
            a[k], b[k] = float(np.mean(x)), float(np.mean(y))
        r = pearson([a[k] for k in ids], [b[k] for k in ids])
        if not np.isnan(r):
            rs.append(r)
        qa, qb = quartile_index(a), quartile_index(b)
        agree.append(float(np.mean([qa[k] == qb[k] for k in ids])))
        near.append(float(np.mean([abs(qa[k] - qb[k]) <= 1 for k in ids])))
    r = float(np.mean(rs)) if rs else float("nan")
    return {"places": len(ids), "r": r, "r_lo": float(np.percentile(rs, 2.5)) if rs else float("nan"), "r_hi": float(np.percentile(rs, 97.5)) if rs else float("nan"),
            "reliability": spearman_brown(r), "same_quartile": float(np.mean(agree)), "within_one_quartile": float(np.mean(near))}


def icc1(groups: dict[str, list[float]]) -> tuple[float, float]:
    """(ICC(1), the typical group size): one-way random effects, unbalanced groups. NaN when there is no variance to split."""
    gs = [np.array(v, float) for v in groups.values() if len(v) >= 2]
    g = len(gs)
    if g < 3:
        return float("nan"), float("nan")
    n_i = np.array([len(x) for x in gs], float)
    big_n = n_i.sum()
    grand = np.concatenate(gs).mean()
    ssb = sum(len(x) * (x.mean() - grand) ** 2 for x in gs)
    ssw = sum(((x - x.mean()) ** 2).sum() for x in gs)
    msb, msw = ssb / (g - 1), ssw / (big_n - g)
    k0 = (big_n - (n_i ** 2).sum() / big_n) / (g - 1)
    denom = msb + (k0 - 1) * msw
    return (float((msb - msw) / denom) if denom > 0 else float("nan")), float(np.median(n_i))


def reliability_of_mean(icc: float, n: float) -> float:
    return n * icc / (1 + (n - 1) * icc) if not np.isnan(icc) and icc > 0 else float("nan")


def reviews_needed(icc: float, target: float) -> float:
    """How many reviews a place needs for the mean of its scores to reach `target` reliability, given ICC(1) of single reviews."""
    return target * (1 - icc) / (icc * (1 - target)) if not np.isnan(icc) and icc > 0 else float("nan")


def composite_split_half(obs: dict[str, dict[str, list[float]]], min_n: int, rng: random.Random, n_splits: int = SPLITS) -> dict:
    """Split-half for the composite: places with at least min_n mentions of every aspect; each aspect's mentions are halved separately, the half
    scores are combined with the frozen weights w1, and the two composites are correlated across places."""
    ids = [p for p in obs[ASPECTS[0]] if all(len(obs[a].get(p, [])) >= max(min_n, 4) for a in ASPECTS)]
    rs = []
    for _ in range(n_splits):
        ca, cb = [], []
        for p in ids:
            ha, hb = {}, {}
            for a in ASPECTS:
                ha[a], hb[a] = (float(np.mean(x)) for x in halves(obs[a][p], rng))
            ca.append(sum(WEIGHTS[a] * ha[a] for a in ASPECTS))
            cb.append(sum(WEIGHTS[a] * hb[a] for a in ASPECTS))
        r = pearson(ca, cb)
        if not np.isnan(r):
            rs.append(r)
    r = float(np.mean(rs)) if rs else float("nan")
    return {"places": len(ids), "r": r, "reliability": spearman_brown(r)}


def place_correlations(obs: dict[str, dict[str, list[float]]], stars: dict[str, list[float]], min_n: int = 10) -> dict:
    """Context for reading the reliabilities: across places with at least min_n mentions of every aspect, the correlation of the place means of the four
    aspects with each other and with Yelp's stars. A reliable score that is only the star rating again would add nothing."""
    ids = [p for p in stars if all(len(obs[a].get(p, [])) >= min_n for a in ASPECTS)]
    series = {**{a: [float(np.mean(obs[a][p])) for p in ids] for a in ASPECTS}, "stars": [float(np.mean(stars[p])) for p in ids]}
    names = list(series)
    return {"places": len(ids), "names": names, "matrix": [[pearson(series[x], series[y]) for y in names] for x in names]}


def fmt(x: float, spec: str = ".2f") -> str:
    return "n/a" if np.isnan(x) else format(x, spec)


# ---- reading the database -------------------------------------------------------------------------------------------------------------

def load(conn) -> tuple[dict[str, dict[str, list[float]]], dict[str, list[float]]]:
    """({aspect: {place: [scores of the reviews that mention it]}}, {place: [Yelp stars of every review]}) from the full scoring run."""
    run_id = conn.execute("SELECT max(id) FROM aspect_run WHERE n_reviews > 1000").fetchone()[0]
    obs: dict[str, dict[str, list[float]]] = {a: defaultdict(list) for a in ASPECTS}
    for place, aspect, score in conn.execute(
            "SELECT pr.place_id, s.aspect, s.score FROM place_review pr JOIN aspect_score s ON s.review_id = pr.review_id AND s.run_id = %s "
            "WHERE s.mentioned >= %s", (run_id, MENTION)):
        obs[aspect][str(place)].append(float(score))
    stars: dict[str, list[float]] = defaultdict(list)
    for place, st in conn.execute("SELECT pr.place_id, pr.stars FROM place_review pr WHERE pr.review_id IN (SELECT review_id FROM aspect_request WHERE run_id = %s AND error IS NULL)", (run_id,)):
        stars[str(place)].append(float(st))
    return obs, stars


def analyse(obs: dict[str, dict[str, list[float]]], stars: dict[str, list[float]], seed: int = SEED) -> dict:
    rng = random.Random(seed)
    out: dict = {"aspects": {}, "composite": {}}
    for name, groups in (*obs.items(), ("stars", stars)):
        icc, typical = icc1({k: v for k, v in groups.items() if len(v) >= 2})
        out["aspects"][name] = {
            "icc": icc, "typical_n": typical, "needed_07": reviews_needed(icc, 0.7), "needed_08": reviews_needed(icc, 0.8), "by_min_n": {},
            "reviews_total": sum(len(v) for v in groups.values()), "places_any": len(groups),
        }
        for k in MIN_NS:
            out["aspects"][name]["by_min_n"][k] = split_half({p: v for p, v in groups.items() if len(v) >= k}, rng)
    for k in MIN_NS:
        out["composite"][k] = composite_split_half(obs, k, rng)
    out["correlations"] = place_correlations(obs, stars)
    return out


def render(res: dict) -> str:
    lines = ["# Reliability of place-level aspect scores (PRIVATE: derived from the Yelp Data)", ""]
    lines.append("Gitignored on purpose (`docs/private/`; agreement sections 4E and 5). The method is in `docs/decisions/0034-aspect-reliability.md`. "
                 "Reproduce: `.venv/bin/python -m streetwalker.aspect_split_half --write`.")
    lines.append("")
    lines.append("Reviews that mention the aspect (probability 0.5 or more), grouped by place; 200 random splits. Reliability is the Spearman-Brown step-up of the "
                 "half-to-half correlation: how reliable the mean over all of a place's mentions is. `stars` is Yelp's own rating of every review of the place.")
    lines.append("")
    for k in MIN_NS:
        lines += [f"## Places with at least {k} mentions", "", "| Aspect | Places | Half-to-half r [95% of splits] | Reliability (full mean) | Same quartile in both halves | Within one quartile |", "|---|---|---|---|---|---|"]
        for name, a in res["aspects"].items():
            s = a["by_min_n"][k]
            lines.append(f"| {name} | {s['places']} | {fmt(s['r'])} [{fmt(s['r_lo'])}, {fmt(s['r_hi'])}] | {fmt(s['reliability'])} | {fmt(s['same_quartile'], '.0%')} | {fmt(s['within_one_quartile'], '.0%')} |")
        c = res["composite"][k]
        lines.append(f"| composite (w1) | {c['places']} | {fmt(c['r'])} | {fmt(c['reliability'])} | | |")
        lines.append("")
    c = res["correlations"]
    lines += [f"## Context: how the place means relate to each other and to the stars ({c['places']} places with at least 10 mentions of every aspect)", "",
              "| | " + " | ".join(c["names"]) + " |", "|---|" + "---|" * len(c["names"])]
    lines += [f"| {n} | " + " | ".join(fmt(v) for v in row) + " |" for n, row in zip(c["names"], c["matrix"], strict=True)]
    lines += ["", "## How much of one review says something about its place (ICC(1)), and what that implies", "", "| Aspect | Reviews | ICC(1) | Typical mentions per place | Mentions needed for reliability 0.7 | for 0.8 |", "|---|---|---|---|---|---|"]
    for name, a in res["aspects"].items():
        lines.append(f"| {name} | {a['reviews_total']} | {fmt(a['icc'], '.3f')} | {fmt(a['typical_n'], '.0f')} | {fmt(a['needed_07'], '.0f')} | {fmt(a['needed_08'], '.0f')} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help=f"write the private report to {REPORT}")
    args = ap.parse_args()
    from streetwalker import db

    with db.connect() as conn:
        obs, stars = load(conn)
    text = render(analyse(obs, stars))
    print(text)
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(text)
        print(f"written to {REPORT}")


if __name__ == "__main__":
    main()
