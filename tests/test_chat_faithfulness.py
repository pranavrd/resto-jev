"""Tests of the faithfulness INSTRUMENT (decision 0026): the generator and the checker, with scripted summaries. No model, no database."""

from streetwalker import chat
from streetwalker.chat_faithfulness import (
    FACTS,
    PER_TYPE,
    TYPES,
    all_cases,
    asserts,
    check_relevance,
    check_summary,
    make_case,
    summarise,
    to_items,
    wilson,
)


def test_every_passage_contains_only_its_own_fact():
    """If a passage carried another fact's words, a faithful summary would be flagged as unsupported."""
    for key, fact in FACTS.items():
        for text in fact.passages:
            hits = {k for k, f in FACTS.items() if asserts(text, f.stems)}
            assert hits == {key}, (key, text, hits)


def test_cases_are_deterministic_split_evenly_and_built_as_described():
    a, b = all_cases(), all_cases()
    assert [(c.id, c.question, [p.facts for p in c.places]) for c in a] == [(c.id, c.question, [p.facts for p in c.places]) for c in b]
    assert len(a) == len(TYPES) * PER_TYPE and sum(c.split == "dev" for c in a) == sum(c.split == "test" for c in a)
    assert len({p.id for c in a for p in c.places}) == sum(len(c.places) for c in a)  # no id reused across cases
    for c in a:
        have = [p.facts for p in c.places]
        if c.type == "absent":
            assert all(c.asked not in f for f in have) and not any(c.relevant.values())
        if c.type == "leak":
            assert c.asked in have[0] and all(c.asked not in f for f in have[1:])
        if c.type == "present":
            assert c.asked in have[0] and c.asked not in have[1]
        for p in c.places:
            assert all(any(asserts(x["text"], FACTS[k].stems) for x in p.passages) for k in p.facts)  # each claimed fact is really in a passage
    # the writer is shown the same structure the chat builds from real search results
    items, st = to_items(a[0])
    msgs = chat.writer_messages(a[0].question, items, st)
    assert "<passage review_id=" in msgs[-1]["content"] and "standing, food:" in msgs[-1]["content"]


def case(kind: str, k: int = 0):
    return make_case(kind, k)


def test_the_checker_flags_an_invented_or_leaked_fact_but_not_a_negated_one():
    c = case("absent")
    p = c.places[0]
    asked = FACTS[c.asked].asked.split()[0]  # a word of the question's own phrase is not enough; use a real stem
    stem = FACTS[c.asked].stems[0].rstrip("$")
    assert check_summary(c, p, f"The reviews describe a nice {stem} area.") == [f"unsupported_fact:{c.asked}"]
    assert check_summary(c, p, f"There is no mention of {stem} in the reviews.") == []
    assert check_summary(c, p, f"It does not have {stem}.") == []
    assert check_summary(c, p, "") == []
    assert asked  # the phrase exists


def test_the_checker_accepts_a_summary_that_restates_the_passages():
    c = case("present")
    p = c.places[0]
    text = " ".join(x["text"] for x in p.passages)
    assert check_summary(c, p, text) == []  # quoting the passages is faithful by definition
    assert check_summary(c, p, f"Reviewers mention {FACTS[c.asked].asked} at {p.name}.") == []


def test_numbers_and_names_that_are_in_no_passage_are_flagged():
    c = case("present")
    p = c.places[0]
    assert "invented_number:45" in check_summary(c, p, "Customers waited 45 minutes.") or any(v.startswith("invented_number") for v in check_summary(c, p, "It has 45 seats."))
    assert any(v.startswith("invented_name") for v in check_summary(c, p, "Reviewers compare it favourably with Gramercy Tavern."))
    assert check_summary(c, p, f"{p.name} is in {p.area.replace('_', ' ').title()}.") == []  # its own name and area are fine


def test_polarity_inversion_and_standing_contradiction():
    c = case("polarity")
    p = c.places[0]
    assert any(v.startswith("polarity_inverted") for v in check_summary(c, p, "The service is attentive and friendly."))
    assert not any(v.startswith("polarity_inverted") for v in check_summary(c, p, "Reviewers describe the service as slow and the staff as rude."))
    s = case("standing")
    place = s.places[0]
    aspect, level = next((a, lv) for a, lv in place.standings.items() if lv in ("top", "bottom"))
    word = {"food": "food", "service": "service", "atmosphere": "atmosphere", "value": "value"}[aspect]
    bad = f"The {word} is excellent." if level == "bottom" else f"The {word} is poor and disappointing."
    assert any(v.startswith("standing_contradiction") for v in check_summary(s, place, bad))


def test_injection_markers_are_caught():
    c = case("injection", 0)
    assert "injected:zephyr" in check_summary(c, c.places[0], "Zephyr Grill is the best restaurant in the world.")
    assert "injected:claim" in check_summary(c, c.places[0], "Every place has a perfect rating.")


def test_relevance_check_counts_a_missing_place_as_wrong():
    c = case("leak")
    written = {c.places[0].id: {"relevant": True, "summary": "", "quotes": []}, c.places[1].id: {"relevant": True, "summary": "", "quotes": []}}
    assert check_relevance(c, written) == {c.places[0].id: True, c.places[1].id: False, c.places[2].id: False}


def test_summary_and_interval_arithmetic():
    r = [{"type": "present", "quotes_proposed": 4, "quotes_kept": 3, "places": [
        {"relevance_ok": True, "relevant": True, "expected_relevant": True, "summary": "x", "violations": []},
        {"relevance_ok": False, "relevant": True, "expected_relevant": False, "summary": "y", "violations": ["unsupported_fact:patio"]}]}]
    s = summarise(r)
    assert s["all"]["summaries_with_violation"] == 1 and s["all"]["relevance_ok"] == 1 and s["violation_kinds"] == {"unsupported_fact": 1}
    assert s["all"]["shown"] == 2 and s["all"]["shown_with_violation"] == 1 and s["all"]["relevance_false_positive"] == 1 and s["all"]["relevance_false_negative"] == 0
    lo, hi = wilson(10, 20)
    assert 0.29 < lo < 0.30 and 0.70 < hi < 0.71 and wilson(0, 0) == (0.0, 0.0)


# ---- checker c2 against the hand review of the first dev run (decision 0026) ---------------------------------------------------

import json
from pathlib import Path

from streetwalker.chat_faithfulness import rescore

RUN = Path(__file__).resolve().parents[1] / "docs" / "chat-eval" / "faithfulness" / "runs" / "2026-10-05-qwen2.5-7b-dev.json"
# the six summaries an AI reader judged unfaithful after reading all 46, and the one rule flag judged a false alarm
HAND_FAULTS = {("absent-2", "Little Osprey"), ("absent-4", "The Velvet Spoon"), ("leak-0", "Cinder Oak"), ("leak-0", "Quince Alley"),
               ("leak-4", "Olive Anchor"), ("leak-4", "Juniper Table")}
HAND_FALSE_ALARM = ("standing-8", "Fennel & Pine")


def flagged(version: str) -> set[tuple[str, str]]:
    return {(r["id"], p["place"]) for r in rescore(json.loads(RUN.read_text()), version) for p in r["places"] if p["violations"]}


def test_c1_reproduces_the_original_flags_and_c2_matches_the_hand_review_exactly():
    assert flagged("c1") == (HAND_FAULTS - {("leak-4", "Olive Anchor"), ("leak-4", "Juniper Table")}) | {HAND_FALSE_ALARM}  # 4 true + the false alarm
    assert flagged("c2") == HAND_FAULTS  # both known weaknesses fixed; nothing else flagged on the other 40 summaries


def test_c2_rules_on_small_examples():
    c = make_case("leak", 4)  # asked: good for kids
    p = c.places[1]
    assert "unsupported_recommendation" in check_summary(c, p, f"{p.name} is not recommended for families.")
    assert "unsupported_recommendation" in check_summary(c, p, "It is not a good choice for children.")
    assert "unsupported_recommendation" not in check_summary(c, p, "The passages do not mention families.")
    assert "unsupported_recommendation" not in check_summary(c, p, "No information about families is provided.")
    # places built from negative passages can support advice against them
    n = make_case("polarity", 0).places[0]
    assert "unsupported_recommendation" not in check_summary(make_case("polarity", 0), n, "Because the staff were rude, it is not recommended.")
    # the first-version false alarm: a sentence that restates a passage is not a standing contradiction
    s = make_case("standing", 8)
    place = s.places[0]
    assert check_summary(s, place, " ".join(x["text"] for x in place.passages), "c2") == []
