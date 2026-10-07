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
from streetwalker.chat_followup_eval import summarise as summarise_followups
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


# ---- multi-turn follow-ups (decision 0031) ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("run", "fully", "plan", "baseline", "flag", "controls"), [
    ("followup-dev-iter1", 12, 13, 9, 15, 4),
    ("followup-dev-iter2", 14, 15, 9, 15, 4),
    ("followup-test", 14, 14, 7, 15, 4),
])
def test_followup_counts_recompute_from_the_saved_rows(run, fully, plan, baseline, flag, controls):
    s = summarise_followups(load("runs", f"2026-10-05-{run}.json")["rows"])
    assert (s["with_history_fully_correct"], s["plan_correct"], s["baseline_plan_correct"], s["followup_flag_ok"], s["controls_unchanged"]) == (fully, plan, baseline, flag, controls)


def test_the_followup_criterion_written_before_the_test_read_is_met_on_the_saved_run():
    s = summarise_followups(load("runs", "2026-10-05-followup-test.json")["rows"])
    assert s["plan_correct"] - s["baseline_plan_correct"] >= 5 and s["followup_flag_ok"] >= 14 and s["controls_unchanged"] == s["controls"] == 4


# ---- decision 0032: the follow-up rewrite r2, planner p3, and the figures that failed their criteria ----------------------------------

@pytest.mark.parametrize(("run", "expected", "n"), [
    ("p2-v4-dev", 7, 24), ("p3-v4-dev-iter1", 24, 24), ("p3-v4-test-iter1", 23, 24),  # v4 is development data for p3: not an estimate
    ("p2-v5-test", 17, 24), ("p3-v5-test", 20, 24),
])
def test_planner_p3_counts_recompute_from_the_saved_plans(run, expected, n):
    assert rescore_run(load("runs", f"2026-10-06-{run}.json")) == (expected, n)


def test_p3_did_not_meet_its_preregistered_criterion_on_v5_and_was_not_made_the_default():
    p2, p3 = rescore_run(load("runs", "2026-10-06-p2-v5-test.json")), rescore_run(load("runs", "2026-10-06-p3-v5-test.json"))
    gain, required = p3[0] - p2[0], 5  # the criterion written before the read was at least +5
    assert gain == 3 and gain < required
    from streetwalker import chat

    assert chat.PLAN_VERSION in ("p2", "p4")  # never p3: p4 only if its own criterion was met (decision 0032)
    assert "NOT met" in (EVAL / "log.md").read_text()


@pytest.mark.parametrize(("run", "counts"), [
    ("r1-v2-dev", (12, 12, 4, 14, 4)), ("r2-v2-dev-iter1", (15, 15, 4, 16, 4)), ("r2-v1-dev-regression", (15, 15, 9, 16, 4)),
    ("r1-v2-test", (14, 14, 5, 14, 4)), ("r2-v2-test", (16, 16, 5, 16, 4)),
])
def test_followup_v2_counts_recompute_from_the_saved_rows(run, counts):
    s = summarise_followups(load("runs", f"2026-10-06-{run}.json")["rows"])
    assert (s["with_history_fully_correct"], s["plan_correct"], s["baseline_plan_correct"], s["followup_flag_ok"], s["controls_unchanged"]) == counts


def test_r2_gain_over_r1_on_the_v2_test_half_was_two_and_its_criterion_of_three_was_not_met():
    r1, r2 = (summarise_followups(load("runs", f"2026-10-06-{r}-v2-test.json")["rows"]) for r in ("r1", "r2"))
    gain, required = r2["with_history_fully_correct"] - r1["with_history_fully_correct"], 3  # the written criterion; unreachable given r1's 14/16, and recorded as not met
    assert gain == 2 and gain < required
    assert r2["controls_unchanged"] == r2["controls"] == 4 and r2["followup_flag_ok"] >= r1["followup_flag_ok"]
    assert "NOT met" in (EVAL / "log.md").read_text() and "badly set" in (EVAL / "log.md").read_text()


def test_the_0031_held_out_result_without_the_one_message_the_prompt_quotes():
    rows = [r for r in load("runs", "2026-10-05-followup-test.json")["rows"] if r["message"] != "in Rittenhouse instead"]  # disclosed in decision 0032
    assert (len(rows), sum(r["plan_ok"] and r["followup_ok"] for r in rows), sum(r["baseline_plan_ok"] for r in rows)) == (15, 13, 7)


@pytest.mark.parametrize(("run", "tp", "fn", "fp", "place_fp"), [
    ("per_passage-dev2", 41, 7, 13, 9), ("k2-dev2", 41, 7, 3, 3), ("k3-dev2", 44, 4, 5, 5),
    ("per_passage-test2", 39, 9, 13, 10), ("k2-test2", 36, 12, 3, 3),
])
def test_this_place_check_counts_recompute_from_the_saved_verdicts(run, tp, fn, fp, place_fp):
    s = summarise_verifier(load("verifier", "runs", f"2026-10-06-{run}.json")["places"])
    assert (s["tp"], s["fn"], s["fp"], s["place_fp"]) == (tp, fn, fp, place_fp)


def test_k2_met_two_of_its_three_preregistered_criteria_and_failed_recall_so_the_default_check_is_unchanged():
    base = summarise_verifier(load("verifier", "runs", "2026-10-06-per_passage-test2.json")["places"])
    cand = summarise_verifier(load("verifier", "runs", "2026-10-06-k2-test2.json")["places"])
    recall = lambda s: s["tp"] / (s["tp"] + s["fn"])
    drop = recall(base) - recall(cand)
    assert base["place_fp"] - cand["place_fp"] >= max(3, base["place_fp"] / 3)  # (a) met
    assert drop > 0.05  # (b) NOT met: 6.3 points
    assert cand["categories"]["injection_no"]["correct"] >= base["categories"]["injection_no"]["correct"]  # (c) met
    from streetwalker import chat

    assert chat.CHECK_VERSION == "k1"
    assert "NOT met" in (EVAL / "verifier" / "log.md").read_text()


@pytest.mark.parametrize(("run", "counts"), [
    ("r1-v3-dev", (14, 14, 9, 18, 8)), ("r2-v3-dev", (17, 17, 10, 20, 9)), ("r3-v3-dev", (18, 18, 13, 22, 12)),
    ("r1-v3-test", (19, 19, 10, 20, 10)), ("r2-v3-test", (17, 17, 9, 20, 9)), ("r3-v3-test", (22, 22, 12, 23, 12)),
    ("r3-v2-dev", (14, 14, 4, 16, 4)), ("r3-v1-dev", (15, 15, 9, 16, 4)),
])
def test_followup_v3_and_r3_counts_recompute_from_the_saved_rows(run, counts):
    s = summarise_followups(load("runs", f"2026-10-06-{run}.json")["rows"])
    assert (s["with_history_fully_correct"], s["plan_correct"], s["baseline_plan_correct"], s["followup_flag_ok"], s["controls_unchanged"]) == counts


def test_r3_met_its_preregistered_criterion_on_v3_test_and_is_the_default():
    r1, r3 = (load("runs", f"2026-10-06-{r}-v3-test.json")["rows"] for r in ("r1", "r3"))
    complete = lambda rows: sum(r["unchanged"] for r in rows if r["control"])
    genuine = lambda rows: sum(r["plan_ok"] and r["followup_ok"] for r in rows if not r["control"])
    assert complete(r3) >= 11  # (a)
    assert genuine(r3) >= genuine(r1)  # (b)
    assert sum(r["followup_ok"] for r in r3) >= sum(r["followup_ok"] for r in r1)  # (c)
    assert (complete(r1), genuine(r1), complete(r3), genuine(r3)) == (10, 9, 12, 10)
    from streetwalker import chat

    assert chat.REWRITE_VERSION == "r3"


def test_r1_rewrote_a_quarter_of_the_complete_questions_that_shared_context_with_the_last_turn():
    rows = [r for s in ("dev", "test") for r in load("runs", f"2026-10-06-r1-v3-{s}.json")["rows"] if r["control"]]
    assert (len(rows), sum(not r["unchanged"] for r in rows)) == (24, 6)  # decision 0031's controls were too easy to show this
