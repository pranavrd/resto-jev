"""The figures in the decision records, recomputed from the committed run files with the current code. No model, no database.

If a scorer, a checker or a summary function changes in a way that moves a published number, this fails, and the change must either be
reverted or the record updated on purpose. Every run file is invented-data output and is committed; none holds Yelp data.
"""

import json
from pathlib import Path

import pytest

from streetwalker.chat_eval import rescore_run
from streetwalker.chat_faithfulness import rescore as rescore_faithfulness
from streetwalker.chat_faithfulness import summarise as summarise_faithfulness
from streetwalker.chat_verifier_eval import summarise as summarise_verifier

EVAL = Path(__file__).resolve().parents[1] / "docs" / "chat-eval"
DECISIONS = Path(__file__).resolve().parents[1] / "docs" / "decisions"


def load(*parts: str) -> dict:
    return json.loads(EVAL.joinpath(*parts).read_text())


# ---- planner (decisions 0025 and 0029) --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("run", "expected"), [
    ("p1-v2-dev-iter1", 18), ("p1-v2-test", 20), ("p1-v3", 19),
    ("p2-v2-dev-iter2", 32), ("p2-v2-test", 32), ("p2-v3", 29), ("p2-v1-dev", 24), ("p2-v1-test", 23),
    ("p2-v2-dev-iter1", 24),  # logged as 23: that run predates scorer v2 (a three-word question that is only a topic was marked wrong)
])
def test_planner_counts_recompute_from_the_saved_plans(run, expected):
    good, n = rescore_run(load("runs", f"2026-10-05-{run}.json"))
    assert (good, n) == (expected, 24 if "-v1-" in run else 32)


def test_the_headline_planner_comparison_in_decision_0029_holds():
    a, b = rescore_run(load("runs", "2026-10-05-p1-v3.json")), rescore_run(load("runs", "2026-10-05-p2-v3.json"))
    assert b[0] - a[0] >= 5  # the pre-registered criterion
    rows1, rows2 = load("runs", "2026-10-05-p1-v3.json")["rows"], load("runs", "2026-10-05-p2-v3.json")["rows"]
    only2 = sum(all(y["ok"].values()) and not all(x["ok"].values()) for x, y in zip(rows1, rows2, strict=True))
    only1 = sum(all(x["ok"].values()) and not all(y["ok"].values()) for x, y in zip(rows1, rows2, strict=True))
    assert (only2, only1) == (13, 3)
    text = (DECISIONS / "0029-planner-v2.md").read_text()
    assert "29/32" in text and "19/32" in text and "13 questions" in text


# ---- writer faithfulness (decisions 0026 and 0027) -------------------------------------------------------------------------------

@pytest.mark.parametrize(("run", "checker", "summaries", "flagged", "shown"), [
    ("2026-10-05-qwen2.5-7b-dev.json", "c1", 46, 5, 28),        # the first dev run as the first checker saw it
    ("2026-10-05-qwen2.5-7b-dev.json", "c2", 46, 6, 28),        # and as checker c2 sees it: the six faults found by hand
    ("2026-10-05-qwen2.5-7b-w1-test.json", "c2", 44, 5, 24),
    ("2026-10-05-qwen2.5-7b-w3-test.json", "c2", 21, 1, 21),
    ("2026-10-05-qwen2.5-7b-w3-dev-final.json", "c2", 26, 0, 26),
])
def test_faithfulness_counts_recompute_from_the_saved_summaries(run, checker, summaries, flagged, shown):
    a = summarise_faithfulness(rescore_faithfulness(load("faithfulness", "runs", run), checker))["all"]
    assert (a["summaries"], a["summaries_with_violation"], a["shown"]) == (summaries, flagged, shown)


def test_the_w1_versus_w3_test_comparison_of_decision_0027_holds():
    w1 = summarise_faithfulness(rescore_faithfulness(load("faithfulness", "runs", "2026-10-05-qwen2.5-7b-w1-test.json"), "c2"))["all"]
    w3 = summarise_faithfulness(rescore_faithfulness(load("faithfulness", "runs", "2026-10-05-qwen2.5-7b-w3-test.json"), "c2"))["all"]
    assert (w1["relevance_false_positive"], w1["relevance_false_negative"]) == (3, 9) and (w3["relevance_false_positive"], w3["relevance_false_negative"]) == (1, 8)
    assert w1["quotes_kept"] == w1["quotes_proposed"] == 31 and w3["quotes_kept"] == w3["quotes_proposed"] == 26


# ---- relevance check (decision 0028) -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("run", "tp", "fn", "fp"), [
    ("per_passage-dev", 42, 6, 11), ("per_passage-test", 43, 5, 2),
    ("grouped_light-dev", 43, 5, 0), ("grouped_light-test", 39, 9, 2),
    ("stance-dev", 30, 18, 1), ("per_passage_sanitized-dev", 43, 5, 12),
])
def test_relevance_check_counts_recompute_from_the_saved_verdicts(run, tp, fn, fp):
    s = summarise_verifier(load("verifier", "runs", f"2026-10-05-{run}.json")["places"])
    assert (s["tp"], s["fn"], s["fp"]) == (tp, fn, fp)


def test_the_candidate_failed_its_preregistered_criterion_on_the_saved_test_runs():
    base = summarise_verifier(load("verifier", "runs", "2026-10-05-per_passage-test.json")["places"])
    cand = summarise_verifier(load("verifier", "runs", "2026-10-05-grouped_light-test.json")["places"])
    recall = lambda s: s["tp"] / (s["tp"] + s["fn"])
    assert not cand["place_fp"] < base["place_fp"]  # (a) not lower
    assert recall(cand) < recall(base) - 0.05  # (b) more than 5 points below
