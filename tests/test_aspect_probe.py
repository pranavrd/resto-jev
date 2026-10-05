import re

import numpy as np
import pytest

from streetwalker.aspect_probe import (
    CUES,
    FRAGMENTS,
    HARD_CASES,
    WRAPPERS,
    build_probes,
    evaluate,
    judge_hard,
)
from streetwalker.aspects import ASPECTS


def cues_in(text: str) -> set[str]:
    low = text.lower()
    return {a for a, words in CUES.items() if any(re.search(r"\b" + re.escape(w), low) for w in words)}  # word starts: "overpriced" is not "rice"


def test_the_set_has_the_planned_shape_and_is_deterministic():
    probes = build_probes()
    assert probes == build_probes() and build_probes(1) != probes
    kinds = [p["kind"] for p in probes]
    assert kinds.count("wrapped") == 4 * 5 * 3 * 2 and kinds.count("control") == 20 and kinds.count("cross") == 36
    assert len({p["id"] for p in probes}) == len(probes)


def test_every_fragment_is_about_its_own_aspect_and_no_other():
    for aspect, levels in FRAGMENTS.items():
        assert set(levels) == {0, 1, 2, 3, 4} and all(len(v) == 3 for v in levels.values())
        for level, texts in levels.items():
            assert len(set(texts)) == 3
            for t in texts:
                assert cues_in(t) == {aspect}, f"{aspect} level {level} should mention only its own aspect: {t!r}"


def test_the_tone_sentences_say_nothing_about_any_aspect():
    for tone, sentences in WRAPPERS.items():
        for s in sentences:
            assert cues_in(s) == set(), f"{tone} wrapper leaks an aspect: {s!r}"


def test_a_wrapped_pair_differs_only_in_its_tone_sentence():
    probes = {p["id"]: p for p in build_probes()}
    pos = probes["w:service:0:1:pos"]
    neg = probes["w:service:0:1:neg"]
    fragment = FRAGMENTS["service"][0][1]
    assert fragment in pos["text"] and fragment in neg["text"]
    assert pos["fragment"] == neg["fragment"] and pos["expect"] == neg["expect"] and pos["tone"] != neg["tone"]
    assert pos["text"].replace(fragment, "") != neg["text"].replace(fragment, "")


def test_expectations_mention_exactly_the_aspects_present():
    for p in build_probes():
        said = {a for a, v in p["expect"].items() if v is not None}
        assert said == cues_in(p["text"]), p["text"]
        if p["kind"] == "cross":
            (_a, la), (_b, lb) = p["levels"].items()
            assert (la <= 1) != (lb <= 1)  # one clearly negative, one clearly positive


def planted(halo: float = 0.0, leak: float = 0.0, seed: int = 0, miss: float = 0.0):
    """Invented 'Jev answers': the true level plus a halo from the tone sentence and a leak from the other aspect."""
    rng = np.random.default_rng(seed)
    results = []
    for p in build_probes():
        jev = {}
        for a in ASPECTS:
            lv = p["expect"][a]
            mention = 0.95 if (lv is not None and rng.random() > miss) or (lv is None and rng.random() < miss) else 0.05
            score = 2.0
            if lv is not None:
                score = lv + rng.normal(0, 0.2)
                if p["kind"] == "wrapped":
                    score += halo * (1 if p["tone"] == "pos" else -1)
                if p["kind"] == "cross":
                    other = next(v for k, v in p["levels"].items() if k != a)
                    score += leak * (other - lv)
            jev[a] = {"mentioned": mention, "score": float(np.clip(score, 0, 4)), "confidence": 0.8}
        results.append({**p, "jev": jev})
    return results


def test_no_halo_gives_a_gap_near_zero_and_a_planted_halo_is_found():
    clean = evaluate(planted(0.0))["halo"]
    assert abs(clean["all"]["gap"]) < 0.1 and clean["all"]["lo"] <= 0 <= clean["all"]["hi"]
    biased = evaluate(planted(0.4))["halo"]
    # +0.4 for a positive wrapper and -0.4 for a negative one would give 0.8, but scores cannot leave 0 to 4, so the extremes lose some
    assert 0.5 < biased["all"]["gap"] < 0.85 and biased["all"]["lo"] > 0.4
    assert all(biased[a]["gap"] > 0.5 for a in ASPECTS)


def test_leakage_between_aspects_is_measured():
    assert abs(evaluate(planted(leak=0.0))["leakage"]["other_aspect_level"]) < 0.1
    assert evaluate(planted(leak=0.3))["leakage"]["other_aspect_level"] == pytest.approx(0.3, abs=0.1)


def test_level_and_mention_metrics():
    good = evaluate(planted())
    assert all(v["within1"] == 1.0 and v["mae"] < 0.3 for v in good["level"].values())
    assert all(m["recall"] == 1.0 and m["false_mention"] == 0.0 for m in good["mention"].values())
    assert good["control_false_mention"] == 0.0
    sloppy = evaluate(planted(miss=0.3))
    assert all(m["recall"] < 0.9 for m in sloppy["mention"].values()) and sloppy["control_false_mention"] > 0.1


def test_request_errors_are_counted_not_hidden():
    results = planted()
    results[0] = {k: v for k, v in results[0].items() if k != "jev"} | {"error": "timeout"}
    out = evaluate(results)
    assert out["errors"] == 1 and out["n"] == len(results)


def test_hard_cases_are_well_formed():
    assert len(HARD_CASES) >= 18 and len({c["text"] for c in HARD_CASES}) == len(HARD_CASES)
    for c in HARD_CASES:
        assert set(c["expect"]) <= set(ASPECTS)
        for lo_hi in c["expect"].values():
            assert lo_hi is None or 0 <= lo_hi[0] <= lo_hi[1] <= 4


def test_judging_a_hard_case_uses_mention_and_a_range_with_slack():
    case = {"expect": {"food": (3, 4), "atmosphere": None, "service": None, "value": None}}
    def jev(food, m=0.95, others=0.05):
        got = {a: {"mentioned": others, "score": 2.0, "confidence": 0.9} for a in ASPECTS}
        got["food"] = {"mentioned": m, "score": food, "confidence": 0.9}
        return {**case, "jev": got}
    assert all(judge_hard(jev(3.4)).values())
    assert judge_hard(jev(2.6))["food"] and not judge_hard(jev(2.4))["food"]  # half a level of slack, no more
    assert not judge_hard(jev(3.5, m=0.2))["food"]  # right score, but Jev says it is not mentioned
    assert not judge_hard(jev(3.5, others=0.9))["service"]  # an aspect nobody mentioned, flagged as mentioned
