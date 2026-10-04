"""Rating tests on invented reviews: Yelp data never enters the repository."""

import importlib
import inspect

import numpy as np
import psycopg
import pytest

from streetwalker import db, rating
from streetwalker.aspects import ASPECTS
from streetwalker.rating import (
    BANNER,
    DEFAULT,
    HALF_LIFE_YEARS,
    WEIGHTS,
    WEIGHTS_VERSION,
    Params,
    Stats,
    composite_draws,
    estimate_kappa,
    fit,
    place_stats,
    posterior,
    rank_intervals,
    recency_weight,
)


def test_the_composite_weights_are_frozen_positive_and_sum_to_one():
    assert WEIGHTS_VERSION == "w1" and set(WEIGHTS) == set(ASPECTS)
    assert all(w > 0 for w in WEIGHTS.values()) and sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert WEIGHTS["food"] == max(WEIGHTS.values()) and WEIGHTS["value"] == min(WEIGHTS.values())


def test_the_rating_code_never_reads_the_label_tables():
    # the labels judge the aspect scores; if this code could read them, the same labels could pick the weights and judge them
    source = inspect.getsource(rating)
    assert "aspect_label" not in source
    assert "human_label" not in source


def test_recency_weight_halves_every_half_life_and_can_be_switched_off():
    assert recency_weight(0, 3.0) == 1.0
    assert recency_weight(3.0, 3.0) == pytest.approx(0.5) and recency_weight(6.0, 3.0) == pytest.approx(0.25)
    assert recency_weight(10.0, None) == 1.0
    assert recency_weight(-1.0, 3.0) == 1.0  # a review dated after the reference is not up-weighted


def test_effective_sample_size_shrinks_when_weights_are_uneven():
    even = place_stats([(0.8, 1.0)] * 10)
    assert even.n_eff == pytest.approx(10) and even.mean == pytest.approx(0.8)
    uneven = place_stats([(0.8, 1.0)] * 5 + [(0.8, 0.1)] * 5)
    assert uneven.n_eff < 10 and uneven.mean == pytest.approx(0.8)
    assert place_stats([]).n_eff == 0 and np.isnan(place_stats([]).mean)
    assert place_stats([(0.5, 0.0)]).n_eff == 0  # a review that does not mention the aspect adds nothing


def test_pseudo_counts_add_up_to_the_effective_sample_size():
    s = place_stats([(1.0, 1.0), (0.0, 0.5), (0.5, 0.25)])
    assert s.alpha + s.beta == pytest.approx(s.n_eff)


def test_a_place_with_few_mentions_is_pulled_to_the_average_and_one_with_many_is_not():
    few = place_stats([(1.0, 1.0)] * 2)
    many = place_stats([(1.0, 1.0)] * 400)
    m_few, lo_few, hi_few, *_ = posterior(few, mu0=0.6, kappa=12)
    m_many, lo_many, hi_many, *_ = posterior(many, mu0=0.6, kappa=12)
    assert 0.6 < m_few < 0.85 < m_many <= 1.0  # two perfect reviews are not trusted, four hundred are
    assert (hi_few - lo_few) > 3 * (hi_many - lo_many)  # and the interval says so
    assert posterior(Stats(0, 0, float("nan"), 0, 0, 0), 0.6, 12)[0] == pytest.approx(0.6)  # no evidence: the prior, unchanged


def test_prior_strength_is_weak_when_places_differ_a_lot_and_strong_when_they_do_not():
    rng = np.random.default_rng(0)

    def stats(means, n=60, noise=0.15):
        return [place_stats([(float(np.clip(m + rng.normal(0, noise), 0, 1)), 1.0) for _ in range(n)]) for m in means]

    different = estimate_kappa(stats(np.linspace(0.2, 0.9, 30)), 0.55)
    alike = estimate_kappa(stats(np.full(30, 0.55) + rng.normal(0, 0.01, 30)), 0.55)
    assert alike > 5 * different


def test_composite_draws_respect_the_weights_and_the_posteriors():
    rng = np.random.default_rng(1)
    posts = {a: (200.0, 50.0) for a in ASPECTS}  # every aspect at about 0.8
    d = composite_draws(posts, WEIGHTS, rng, 2000)
    assert d.mean() == pytest.approx(0.8, abs=0.01)
    skew = {**posts, "food": (50.0, 200.0)}  # food at about 0.2
    assert composite_draws(skew, WEIGHTS, rng, 2000).mean() < d.mean() - 0.2  # food carries 40%


def test_rank_intervals_are_ordered_and_wide_where_places_overlap():
    rng = np.random.default_rng(2)
    clear = np.vstack([rng.normal(m, 0.01, 500) for m in (0.9, 0.5, 0.1)])
    rank, lo, hi = rank_intervals(clear)
    assert list(rank) == [1, 2, 3] and list(lo) == list(hi) == [1, 2, 3]  # well separated: no doubt
    close = np.vstack([rng.normal(m, 0.2, 500) for m in (0.52, 0.5, 0.48)])
    _, lo2, hi2 = rank_intervals(close)
    assert all(h - low >= 1 for low, h in zip(lo2, hi2, strict=True))  # overlapping places could swap


def _reviews(places=12, per=40, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for p in range(places):
        level = 0.2 + 0.7 * p / (places - 1)  # place 0 is worst, the last is best
        for _ in range(per):
            stars = int(np.clip(round(1 + 4 * level + rng.normal(0, 0.8)), 1, 5))
            aspects = {a: (0.9, float(np.clip(4 * level + rng.normal(0, 0.6), 0, 4))) for a in ASPECTS}
            out.append({"place_id": p, "stars": stars, "age_years": float(rng.uniform(0, 8)), "aspects": aspects})
    return out


def test_fit_recovers_the_ordering_and_is_deterministic():
    reviews = _reviews()
    a, b = fit(reviews, DEFAULT), fit(reviews, DEFAULT)
    assert a["composite"] == b["composite"]
    ranks = [a["composite"][p]["rank"] for p in range(12)]
    assert ranks == list(range(12, 0, -1))  # the best place (the last) is rank 1
    assert all(a["composite"][p]["lo"] <= a["composite"][p]["mean"] <= a["composite"][p]["hi"] for p in range(12))
    assert all(1.0 <= a["composite"][p]["mean"] <= 5.0 for p in range(12))


def test_old_reviews_count_for_less_when_recency_is_on():
    new = [{"place_id": 0, "stars": 5, "age_years": 0.1, "aspects": {a: (1.0, 4.0) for a in ASPECTS}}] * 30
    old = [{"place_id": 0, "stars": 1, "age_years": 12.0, "aspects": {a: (1.0, 0.0) for a in ASPECTS}}] * 30
    filler = [{"place_id": 1, "stars": 3, "age_years": 1.0, "aspects": {a: (1.0, 2.0) for a in ASPECTS}}] * 30
    with_recency = fit(new + old + filler, Params(WEIGHTS, 3.0))["composite"][0]["mean"]
    without = fit(new + old + filler, Params(WEIGHTS, None))["composite"][0]["mean"]
    assert with_recency > without + 0.5  # twelve-year-old complaints fade, so the place looks better


def test_the_banner_prints_at_the_top_and_bottom_of_every_summary(capsys):
    reviews = _reviews(places=8)
    result = fit(reviews, DEFAULT)

    class NoDb:
        def execute(self, *a, **k):
            raise AssertionError("no query needed without --table")

    rating.print_summary(NoDb(), result, reviews, table=False)
    out = capsys.readouterr().out
    assert out.count(BANNER) == 2 and out.index(BANNER) < 200 and "frozen, not tuned on labels" in out
    assert HALF_LIFE_YEARS == 3.0


def _ready() -> bool:
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1 FROM rating_run LIMIT 1")
            return True
    except (psycopg.Error, KeyError):
        return False


@pytest.mark.skipif(not _ready(), reason="needs the local DB with migration 021")
def test_the_database_refuses_anything_but_provisional():
    importlib.reload(rating)
    with db.connect() as conn:
        run = conn.execute("SELECT max(id) FROM aspect_run").fetchone()[0]
        if run is None:
            pytest.skip("no aspect run")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("INSERT INTO rating_run (aspect_run_id, weights_version, params, status) VALUES (%s, 'w1', '{}'::jsonb, 'final')", (run,))
        conn.rollback()
