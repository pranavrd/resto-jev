"""The evaluation logic on invented labels, with a halo planted on purpose."""

import numpy as np
import pytest

from streetwalker.aspect_label_report import (
    confidence_vs_error,
    consistency,
    error_correlation,
    halo,
    level_agreement,
    mention_agreement,
    report,
)
from streetwalker.aspects import ASPECTS


def synthetic(n=400, halo_weight=0.0, noise=0.4, seed=0, mention_flip=0.0, shared_error=0.0):
    """The person's level is the truth. Jev's score = (1 - halo) * truth + halo * the stars' tone, plus noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        stars = int(rng.integers(1, 6))
        tone = (stars - 1)  # 0 to 4: the overall tone the stars carry
        human, jev = {}, {}
        offset = rng.normal(0, shared_error) if shared_error else 0.0  # one error shared by every aspect of this review
        for a in ASPECTS:
            mentioned = rng.random() < 0.8
            level = int(np.clip(round(tone + rng.normal(0, 1.5)), 0, 4)) if mentioned else None  # people differ from the stars
            human[a] = level
            says = mentioned if rng.random() > mention_flip else not mentioned
            score = 2.0 if level is None else (1 - halo_weight) * level + halo_weight * tone + rng.normal(0, noise) + offset
            jev[a] = (0.95 if says else 0.05, float(np.clip(score, 0, 4)), float(np.clip(0.9 - abs(rng.normal(0, noise)) * 0.5, 0.2, 1)))
        rows.append({"item_id": i, "review_id": f"r{i}", "stratum": "random", "repeat_of": None, "stars": stars, "place_id": i % 40, "human": human, "jev": jev})
    return rows


def test_no_halo_means_the_stars_add_nothing_once_the_persons_level_is_known():
    h = halo(synthetic(halo_weight=0.0), "food")
    assert h["human_weight"] > 0.9 and abs(h["stars_weight"]) < 0.08
    assert h["stars_lo"] <= h["stars_weight"] <= h["stars_hi"]


def test_a_planted_halo_shows_up_as_weight_on_the_stars():
    h = halo(synthetic(halo_weight=0.35), "food")
    assert h["stars_weight"] == pytest.approx(0.35, abs=0.1)
    assert h["stars_lo"] > 0.15  # the interval excludes zero
    assert h["human_weight"] == pytest.approx(0.65, abs=0.1)


def test_mention_agreement_is_perfect_when_jev_matches_and_degrades_with_flips():
    perfect = mention_agreement(synthetic(), "service")
    assert perfect["precision"] == 1.0 and perfect["recall"] == 1.0 and perfect["kappa"] == pytest.approx(1.0)
    noisy = mention_agreement(synthetic(mention_flip=0.3), "service")
    assert 0.5 < noisy["precision"] < 0.95 and noisy["kappa"] < 0.6


def test_level_agreement_reflects_noise_and_bias():
    tight = level_agreement(synthetic(noise=0.15), "food")
    loose = level_agreement(synthetic(noise=0.9), "food")
    assert tight["exact"] > 0.85 and tight["mae"] < 0.2 and abs(tight["bias"]) < 0.1
    assert loose["mae"] > tight["mae"] + 0.3 and loose["within1"] < 1.0
    assert level_agreement(synthetic(n=3)[:2], "food") == {"n": 0} or level_agreement(synthetic(n=3)[:2], "food")["n"] < 3


def test_confidence_predicts_error_when_it_was_built_to():
    rows = synthetic(noise=0.5)
    thirds = confidence_vs_error(rows, "food")
    assert [t[0] for t in thirds] == ["least confident", "middle", "most confident"]
    assert thirds[0][1] > thirds[2][1]  # the generator makes confidence fall as noise rises


def test_a_shared_per_review_error_makes_errors_move_together():
    shared = error_correlation(synthetic(shared_error=0.9, seed=1))
    independent = error_correlation(synthetic(shared_error=0.0, seed=1))
    assert np.mean([r for r, _ in shared.values()]) > np.mean([r for r, _ in independent.values()]) + 0.3


def test_error_correlation_is_not_a_halo_detector_but_the_stars_weight_is():
    # a halo whose errors are independent across aspects: correlation stays low, the regression still finds it
    rows = synthetic(halo_weight=0.5, seed=2)
    assert np.mean([r for r, _ in error_correlation(rows).values()]) < 0.25
    assert halo(rows, "service")["stars_lo"] > 0.2


def test_consistency_compares_a_repeat_with_its_original():
    rows = synthetic(n=30)
    twin = []
    for k, r in enumerate(rows[:10]):
        human = dict(r["human"])
        if k < 3:
            human["food"] = None if human["food"] is not None else 2  # the labeller changed their mind on three
        twin.append({**r, "item_id": 1000 + k, "stratum": "repeat", "repeat_of": r["item_id"], "human": human})
    out = consistency(rows + twin)
    assert out["pairs"] == 10 and 0.9 < out["mention_agreement"] < 1.0
    assert out["exact"] > 0.9 and out["within1"] >= out["exact"]
    assert consistency(rows) == {"pairs": 0}


def test_the_report_runs_and_keeps_the_parts_apart(capsys):
    rows = synthetic(n=120)
    for k, r in enumerate(rows):
        r["stratum"] = ("random", "value_probe", "divergence_probe")[k % 3]
    report(rows)
    out = capsys.readouterr().out
    assert out.startswith("NOT A RESULT UNTIL BATCH 1") and out.count("=====") >= 6
    assert "random (n=40)" in out and "value_probe (n=40)" in out and "divergence_probe (n=40)" in out
