"""The reliability checks on aspect scores (decision 0034): the pure parts, on invented data. No scorer, no model, no database, no Yelp data."""

import random
from pathlib import Path

import numpy as np

from streetwalker import aspect_split_half as sh
from streetwalker import aspect_stability as st
from streetwalker.aspects import ASPECTS

# ---- stability: the variants ----------------------------------------------------------------------------------------------------------

TEXT = "The pasta was great. Our waiter was slow!! We paid too much."


def test_shuffle_keeps_every_sentence_and_changes_the_order_or_gives_up():
    out = st.shuffle_sentences(TEXT, random.Random(1))
    assert out != TEXT and sorted(st.sentences(out)) == sorted(st.sentences(TEXT))
    assert st.shuffle_sentences("One sentence only.", random.Random(1)) is None
    assert st.shuffle_sentences("Same. Same.", random.Random(1)) is None  # no different order exists


def test_typographic_noise_changes_no_word():
    assert st.typographic_noise("The  Pasta   was GREAT!!!  Really...") == "the pasta was great! really."
    assert st.typographic_noise(TEXT).split() == [w.lower().replace("!!", "!") for w in TEXT.split()]


def test_a_paraphrase_is_rejected_when_its_length_says_content_was_dropped_or_invented():
    class Fake:
        def __init__(self, out):
            self.out = out

        def generate(self, messages, schema):
            return {"text": self.out}

    assert st.paraphrase(Fake("The pasta was excellent. The waiter was sluggish. The bill was steep."), TEXT)
    assert st.paraphrase(Fake("Fine."), TEXT) is None and st.paraphrase(Fake(TEXT * 3), TEXT) is None and st.paraphrase(Fake("  "), TEXT) is None
    assert st.paraphrase(type("B", (), {"generate": lambda self, m, s: {"text": 5}})(), TEXT) is None


def test_the_reworded_questions_keep_the_scale_and_change_the_words():
    from streetwalker.aspects import build_questions

    a, b = build_questions(), st.build_questions_reworded()
    assert set(a) == set(b)
    for name in a:
        assert a[name].instructions != b[name].instructions
        if name.endswith("_sentiment"):
            assert a[name].criteria == b[name].criteria  # the same five level descriptions


def test_make_variants_leaves_out_the_texts_a_variant_cannot_change():
    texts = {"a": TEXT, "b": "Just one sentence."}
    made = st.make_variants(texts, ("repeat", "shuffle", "noise", "prompt"))
    assert set(made["repeat"][0]) == {"a", "b"} and set(made["shuffle"][0]) == {"a"} and made["prompt"][1] is not None and made["repeat"][1] is None


# ---- stability: the metrics -----------------------------------------------------------------------------------------------------------

def score(m, s):
    return {"mentioned": m, "score": s, "confidence": 0.9}


def test_compare_counts_mention_flips_and_polarity_flips_and_only_measures_levels_where_both_mention():
    assert st.compare({"food": score(0.9, 4.0)}, {"food": score(0.2, 1.0)}, "food") == {"mention_flip": True, "both": False, "diff": None, "polarity_flip": False, "a": 4.0, "b": 1.0}
    flip = st.compare({"food": score(0.9, 3.5)}, {"food": score(0.9, 0.5)}, "food")
    assert flip["both"] and flip["diff"] == 3.0 and flip["polarity_flip"] and not flip["mention_flip"]
    near_mid = st.compare({"food": score(0.9, 2.2)}, {"food": score(0.9, 1.8)}, "food")
    assert not near_mid["polarity_flip"]  # crossing the middle by a hair is not a flip of opinion
    assert st.compare({}, {"food": score(0.9, 1.0)}, "food") is None


def test_summarise_gives_zero_difference_for_identical_scores_and_a_correlation_of_one():
    base = [{a: score(0.9, float(i % 5)) for a in ASPECTS} for i in range(12)]
    s = st.summarise([(b, b) for b in base])
    assert s["all"]["mean_abs"] == 0.0 and s["all"]["ge_half"] == 0.0 and s["food"]["mention_flip"] == 0.0 and s["food"]["spearman"] > 0.99
    moved = st.summarise([(b, {a: score(0.9, min(4.0, b[a]["score"] + 1.0)) for a in ASPECTS}) for b in base])
    assert 0.5 < moved["all"]["mean_abs"] < 1.0 and moved["all"]["ge_one"] > 0.5  # the ones already at 4 cannot move


def test_the_table_has_one_row_per_variant():
    s = st.summarise([({a: score(0.9, 2.0) for a in ASPECTS},) * 2])
    rows = st.table({"repeat": s, "noise": s})
    assert len(rows) == 4 and rows[2].startswith("| repeat |") and rows[2].endswith("| n/a |")  # every score identical: no rank correlation to report


# ---- split-half reliability -----------------------------------------------------------------------------------------------------------

def synthetic(places=60, per=20, between=1.0, within=1.0, seed=3) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    return {str(p): list(2 + rng.normal(0, between) + rng.normal(0, within, per)) for p in range(places)}


def test_spearman_brown_steps_a_half_correlation_up_to_the_full_sample():
    assert abs(sh.spearman_brown(0.5) - 2 / 3) < 1e-9 and sh.spearman_brown(1.0) == 1.0 and sh.spearman_brown(0.0) == 0.0
    assert np.isnan(sh.spearman_brown(-0.9, 2.0)) or sh.spearman_brown(-0.9) < 0


def test_places_that_really_differ_split_reliably_and_places_that_do_not_split_at_chance():
    real = sh.split_half(synthetic(between=1.0, within=1.0), random.Random(1), 50)
    none = sh.split_half(synthetic(between=0.0, within=1.0), random.Random(1), 50)
    assert real["r"] > 0.7 and real["reliability"] > 0.8 and real["same_quartile"] > 0.5
    assert abs(none["r"]) < 0.25 and none["same_quartile"] < 0.45  # chance is a quarter for the same quartile
    assert none["within_one_quartile"] < 0.85


def test_quartiles_split_the_places_into_four_equal_groups():
    q = sh.quartile_index({str(i): float(i) for i in range(8)})
    assert sorted(q.values()) == [0, 0, 1, 1, 2, 2, 3, 3] and q["7"] == 3 and q["0"] == 0


def test_icc_is_near_zero_without_a_place_effect_and_matches_the_variance_share_with_one():
    assert abs(sh.icc1(synthetic(between=0.0, within=1.0, places=80))[0]) < 0.06
    icc, typical = sh.icc1(synthetic(between=1.0, within=1.0, places=200, per=15))
    assert 0.4 < icc < 0.6 and typical == 15  # variance share is 1 / (1 + 1)
    assert np.isnan(sh.icc1({"a": [1.0, 2.0]})[0])  # too few places to say


def test_reviews_needed_and_the_reliability_of_the_mean_are_each_others_inverse():
    for icc in (0.05, 0.15, 0.4):
        n = sh.reviews_needed(icc, 0.8)
        assert abs(sh.reliability_of_mean(icc, n) - 0.8) < 1e-9
    assert np.isnan(sh.reviews_needed(0.0, 0.8)) and np.isnan(sh.reviews_needed(float("nan"), 0.8))


def test_the_composite_needs_every_aspect_and_uses_the_frozen_weights():
    base = synthetic(places=50, per=16)
    obs = {a: base for a in ASPECTS}
    c = sh.composite_split_half(obs, 8, random.Random(2), 30)
    assert c["places"] == 50 and c["r"] > 0.5
    thin = {**obs, "value": {k: v[:3] for k, v in base.items()}}
    assert sh.composite_split_half(thin, 8, random.Random(2), 5)["places"] == 0  # one aspect too thin: no place qualifies
    assert abs(sum(sh.WEIGHTS.values()) - 1.0) < 1e-9 and sh.WEIGHTS == {"food": 0.40, "service": 0.25, "atmosphere": 0.20, "value": 0.15}


def test_place_correlations_show_an_aspect_that_is_only_the_stars_again():
    rng = np.random.default_rng(5)
    quality = {str(p): rng.normal() for p in range(40)}
    obs = {a: {p: list(2 + (q if a == "food" else rng.normal()) + rng.normal(0, 0.1, 12)) for p, q in quality.items()} for a in ASPECTS}
    stars = {p: list(3 + q + rng.normal(0, 0.1, 12)) for p, q in quality.items()}
    c = sh.place_correlations(obs, stars, 10)
    assert c["places"] == 40 and c["matrix"][c["names"].index("food")][c["names"].index("stars")] > 0.95
    assert abs(c["matrix"][c["names"].index("service")][c["names"].index("stars")]) < 0.5


def test_both_private_reports_go_under_docs_private_which_git_ignores_and_the_probe_results_are_shareable():
    root = Path(sh.__file__).resolve().parents[2]
    assert sh.REPORT == root / "docs" / "private" / "aspect-split-half.md" and st.PRIVATE == root / "docs" / "private" / "aspect-stability.md"
    assert "docs/private/" in (root / ".gitignore").read_text().splitlines()
    assert st.PROBE_STABILITY.parent == root / "docs" / "probe"  # the invented set's results are committed with the probe results of decision 0022


# ---- the committed results on the invented probe set ------------------------------------------------------------------------------------

def test_the_probe_stability_results_recompute_from_the_saved_scores_and_say_what_the_record_says():
    import json

    saved = json.loads(st.PROBE_STABILITY.read_text())
    base = {p["id"]: p["jev"] for p in json.loads(st.PROBE_RESULTS.read_text()) if "jev" in p}
    for variant, scores in saved["scores"].items():
        again = st.summarise([(base[k], scores[k]) for k in scores if k in base])
        assert again["all"]["mean_abs"] == saved["summary"][variant]["all"]["mean_abs"]
    s = {v: x["all"] for v, x in saved["summary"].items()}
    assert saved["n"] == 176 and set(s) == set(st.VARIANTS)
    assert s["repeat"]["mean_abs"] < 0.03 and s["noise"]["mean_abs"] < 0.05  # the scorer is nearly deterministic and ignores typography
    assert s["shuffle"]["mean_abs"] < 0.1 and s["prompt"]["mean_abs"] < 0.1
    assert s["paraphrase"]["mean_abs"] > s["repeat"]["mean_abs"] and s["paraphrase"]["mean_abs"] < 0.2  # the largest change, and still small on clean text
    assert all(x["polarity_flip"] < 0.02 and x["mention_flip"] < 0.02 for x in s.values())
    assert saved["texts_changed"]["paraphrase"] == 175  # one rewrite was rejected for its length
