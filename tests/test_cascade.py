import pytest

from streetwalker.cascade import (
    GATES,
    Row,
    at_threshold,
    choose_tau,
    error_capture,
    full_cascade,
    human_reviews_needed,
    humans_to_reach,
    order_by,
)
from streetwalker.groundtruth import D1_CLASSES


def probs(top: str, p: float) -> dict[str, float]:
    rest = (1 - p) / (len(D1_CLASSES) - 1)
    return {c: (p if c == top else rest) for c in D1_CLASSES}


def row(i, truth="residential", pred="residential", conf=0.9, split="train", group=None, pano=False, photo=False, t1=None, food=False):
    return Row(
        i, "a", split, group or f"g{i}", truth, food, probs(pred, conf), 0.1, probs(pred, conf), conf, conf, photo or pano, pano,
        t1=t1,
    )


def test_pred_conf_and_margin_come_from_the_probabilities():
    r = row(1, pred="commercial", conf=0.7)
    assert (r.pred, r.conf) == ("commercial", 0.7)
    assert r.margin == pytest.approx(0.7 - 0.05)  # the other six classes share 0.3 equally


def test_order_is_most_uncertain_first_and_ties_break_on_id():
    rows = [row(3, conf=0.9), row(1, conf=0.5), row(2, conf=0.5), row(4, conf=0.2)]
    assert [r.building_id for r in order_by(rows, GATES["stack-gbm confidence"])] == [4, 1, 2, 3]


def test_a_gate_that_puts_every_error_first_has_auroc_one_and_full_capture():
    errors = [row(i, truth="commercial", pred="residential", conf=0.4 + i * 0.001) for i in range(10)]
    right = [row(100 + i, conf=0.9 + i * 0.001) for i in range(90)]
    out = error_capture(errors + right, GATES["stack-gbm confidence"], rates=(0.1, 0.2))
    assert out["auroc"] == pytest.approx(1.0)
    assert out["capture"][0.1] == 1.0 and out["capture"][0.2] == 1.0
    assert out["precision"][0.1] == 1.0 and out["precision"][0.2] == 0.5
    worst = error_capture(errors + right, lambda r: r.conf)  # the reverse order
    assert worst["auroc"] == pytest.approx(0.0)


def test_choose_tau_keeps_enough_accuracy_and_the_fewest_escalations():
    # 60 buildings at 0.95 (all right), 30 at 0.7 (2 in 3 right), 30 at 0.4 (1 in 3 right)
    rows = (
        [row(i, conf=0.95) for i in range(60)]
        + [row(100 + i, conf=0.7, truth="residential" if i % 3 else "commercial") for i in range(30)]
        + [row(200 + i, conf=0.4, truth="residential" if i % 3 == 0 else "commercial") for i in range(30)]
    )
    assert choose_tau(rows, 0.99) == 0.95  # only the top block is that accurate
    assert choose_tau(rows, 0.85) == 0.7  # adding the 0.7 block gives 80/90 = 0.89
    assert choose_tau(rows, 0.80) == 0.7  # keeping everyone gives (60 + 20 + 10) / 120 = 0.75, below 0.80, so 0.7 is the floor
    assert choose_tau(rows, 0.9999) == 0.95  # the top block is perfect and large enough


def test_choose_tau_never_splits_a_block_of_equal_confidence():
    # one wrong answer among 100 at the same confidence: the kept set is all of them or none of them
    rows = [row(i, conf=0.9, truth="residential" if i else "commercial") for i in range(100)]
    assert choose_tau(rows, 0.995) is None  # 99% < 99.5%, and no smaller set may be formed from a tie
    assert choose_tau(rows, 0.98) == 0.9


def test_choose_tau_needs_a_minimum_number_of_kept_buildings():
    rows = [row(i, conf=0.99) for i in range(10)] + [row(100 + i, conf=0.5, truth="commercial") for i in range(100)]
    assert choose_tau(rows, 0.99, min_kept=50) is None  # 10 perfect buildings are not enough evidence
    assert choose_tau(rows, 0.99, min_kept=5) == 0.99


def test_at_threshold_counts_and_accuracy_with_an_oracle_human_tier():
    rows = [row(1, conf=0.95), row(2, conf=0.95, truth="commercial"), row(3, conf=0.6, truth="commercial", pano=True),
            row(4, conf=0.5, photo=True), row(5, conf=0.4, truth="mixed-use")]
    o = at_threshold(rows, 0.7)
    assert (o.n, o.escalated, o.kept) == (5, 3, 2)
    assert o.kept_accuracy == 0.5  # of the two kept, one is right
    assert o.accuracy_tier0 == pytest.approx(2 / 5)  # rows 1 and 4
    assert o.accuracy_final == pytest.approx((3 + 1) / 5)  # 3 resolved by the oracle, 1 kept and right
    assert (o.escalated_pano, o.escalated_photo) == (1, 2)  # pano rows count as photo rows too


def test_human_load_curve_is_monotone_and_imagery_ceiling_saves_reviews():
    rows = [row(i, conf=0.3 + i * 0.01, truth="commercial", pano=i % 2 == 0) for i in range(20)] + [row(100 + i, conf=0.99) for i in range(80)]
    plain = human_reviews_needed(rows, GATES["stack-gbm confidence"])
    pano = human_reviews_needed(rows, GATES["stack-gbm confidence"], "pano")
    assert plain[0] == (0.0, pytest.approx(0.8), 0.0)
    assert [p[1] for p in plain] == sorted(p[1] for p in plain)  # accuracy never falls as more is escalated
    assert plain[-1][1] == 1.0 and plain[20][1] == 1.0  # all 20 errors are the first 20 escalated
    assert pano[20][1] == plain[20][1] and pano[20][2] == pytest.approx(0.1)  # half had a panorama, so 10 reviews not 20
    assert humans_to_reach(plain, 1.0) == pytest.approx(0.2)
    assert humans_to_reach(pano, 1.0) == pytest.approx(0.1)
    assert humans_to_reach(plain, 1.01) is None


def test_full_cascade_follows_the_stated_rules():
    good = probs("commercial", 0.95)
    wrong = probs("residential", 0.95)
    rows = [
        row(1, conf=0.95),  # kept, right
        row(2, conf=0.5, truth="commercial", t1=good),  # escalated, Tier 1 confident and right
        row(3, conf=0.5, truth="commercial", t1=wrong),  # escalated, Tier 1 confident and WRONG
        row(4, conf=0.5, truth="commercial"),  # escalated, no image: human
        row(5, conf=0.5, truth="commercial", t1=probs("commercial", 0.3)),  # Tier 1 not confident enough: human
    ]
    none = full_cascade(rows, 0.7, None)
    assert none.accuracy == 1.0 and none.human_share == pytest.approx(4 / 5) and none.tier1_resolved == 0
    run = full_cascade(rows, 0.7, 0.9)
    assert run.tier1_resolved == 2 and run.tier1_correct == 1
    assert run.accuracy == pytest.approx(4 / 5)  # the confident wrong Tier 1 answer costs one building
    assert run.human_share == pytest.approx(2 / 5)
    assert run.escalated == 4
