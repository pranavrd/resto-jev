from types import SimpleNamespace

from streetwalker.groundtruth import D1_CLASSES
from streetwalker.jev_client import parse
from streetwalker.jev_questions import (
    D1_CRITERIA,
    D2_CRITERIA,
    D2_TYPES,
    MODEL_VERSION,
    build_questions,
    build_tier1_questions,
)
from streetwalker.jev_trial import STRATA, Cand, sample_trial


def pool():
    out, i = [], 0
    for d1, n in (("residential", 300), ("commercial", 40), ("mixed-use", 60), ("civic-institutional", 12),
                  ("industrial", 5), ("other", 6), ("vacant", 1)):
        for k in range(n):
            i += 1
            out.append(Cand(i, d1, d1 in ("commercial", "mixed-use") and k % 4 == 0, "tertiary" if k % 5 == 0 else "residential"))
    return out


def test_sample_is_deterministic_unique_and_hits_the_strata():
    a, b = sample_trial(pool()), sample_trial(pool())
    assert [(c.building_id, s) for c, s in a] == [(c.building_id, s) for c, s in b]
    assert len({c.building_id for c, _ in a}) == len(a)
    assert len(a) == sum(n for _, n, _ in STRATA) == 100
    by = {name: sum(1 for _, s in a if s == name) for name, _, _ in STRATA}
    assert by["food_licensed"] == 15 and by["mixed-use"] == 20 and by["vacant"] == 1
    assert all(c.d3_food for c, s in a if s == "food_licensed")
    assert all(c.highway in ("primary", "tertiary") for c, s in a if s == "residential_corridor")


def test_questions_match_the_class_definitions():
    assert set(D1_CRITERIA) == set(D1_CLASSES) and set(D2_CRITERIA) == set(D2_TYPES)
    qs = build_questions()
    assert set(qs) == {"d1", "d2", "d3"}
    assert MODEL_VERSION == "jev-1.13.0"  # pinned, never a moving alias


def test_parse_normalises_choice_and_yes_no_answers():
    resp = SimpleNamespace(answers={
        "d1": SimpleNamespace(type="choice", choice="commercial", confidence=0.8, probabilities={"commercial": 0.8, "residential": 0.2}),
        "d3": SimpleNamespace(type="noul", noul=0.2),
    })
    d1, d3 = parse(resp)
    assert (d1.answer, d1.confidence) == ("commercial", 0.8) and d1.probs["residential"] == 0.2
    assert d3.answer == "false" and d3.confidence == 0.8 and d3.probs == {"yes": 0.2}


def test_tier1_questions_add_d5_without_changing_d1_to_d3():
    qs = build_tier1_questions()
    assert set(qs) == {"d1", "d2", "d3", "d5"}
    base = build_questions()
    assert qs["d1"].instructions == base["d1"].instructions  # same wording, so tier-0 and tier-1 answers are comparable
