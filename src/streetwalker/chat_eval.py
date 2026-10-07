"""Score a chat model's PLANS on the invented question set (docs/chat-eval, decision 0025).

Usage: .venv/bin/python -m streetwalker.chat_eval [--model qwen2.5:7b] [--split dev|test] [--show-misses]

Tune the planner prompt on `dev` only. `--split test` is the held-out half: run it once, at the end, and record it in
docs/chat-eval/log.md. The questions are invented; no Yelp data is involved.
"""

import argparse
import json
import time
from pathlib import Path

from streetwalker.aspects import ASPECTS
from streetwalker.chat import PLAN_VERSION, PLANNERS, OllamaChat, make_plan

EVAL_DIR = Path(__file__).resolve().parents[2] / "docs" / "chat-eval"
SETS = {"v1": EVAL_DIR / "plan_questions.json", "v2": EVAL_DIR / "plan_questions_v2.json", "v3": EVAL_DIR / "plan_questions_v3.json", "v4": EVAL_DIR / "plan_questions_v4.json", "v5": EVAL_DIR / "plan_questions_v5.json", "v6": EVAL_DIR / "plan_questions_v6.json"}


def score(plan, exp: dict, question: str) -> dict[str, bool]:
    """Per-field correctness of one plan against its expected labels. Out-of-scope questions score only in_scope."""
    ok = {"in_scope": plan.in_scope == exp["in_scope"]}
    if not exp["in_scope"]:
        return ok
    if exp["kinds_ok"] is not None:
        ok["kinds"] = sorted(plan.kinds) in [sorted(k) for k in exp["kinds_ok"]]
    ok["area"] = plan.area == exp["area"]
    ok["near_rail"] = plan.near_rail == exp["near_rail"]
    for a in ASPECTS:
        ok[a] = plan.levels[a] in exp[a]
    if exp["sort"] is not None:
        ok["sort"] = plan.sort in exp["sort"]
    topic = plan.topic.lower()
    words = len(topic.split())
    if exp["topic_any"]:
        # scorer v2 (2026-10-05): copying the question is wrong only for a long question; a three-word question that IS a topic ("dog friendly patios") is
        # correctly copied. The first version flagged every copy, which marked correct plans for "Sushi" and "dog friendly patios" wrong.
        copied = topic == question.lower().rstrip("?") and len(question.split()) > 6
        ok["topic"] = any(k in topic for k in exp["topic_any"]) and words <= 8 and not copied
    elif exp["topic_empty"]:
        ok["topic"] = topic == ""
    return ok


def rescore_run(run: dict) -> tuple[int, int]:
    """(fully correct, total) for a saved run, recomputed with the current scorer from the plans it stored. No model is called."""
    from streetwalker.chat import Plan

    questions = {q["q"]: q for q in json.loads(SETS[run["set"]].read_text())["questions"]}
    good = 0
    for r in run["rows"]:
        p = r["plan"]
        plan = Plan(in_scope=p["in_scope"], topic=p["topic"], kinds=p["kinds"], area=p["area"], levels={a: p[a] for a in ASPECTS}, near_rail=p["near_rail"], sort=p["sort"])
        good += all(score(plan, questions[r["q"]], r["q"]).values())
    return good, len(run["rows"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--set", choices=list(SETS), default="v1", dest="qset", help="v1 is the first question set; v2 is the fresh one (decision 0029)")
    ap.add_argument("--planner", choices=list(PLANNERS), default=PLAN_VERSION)
    ap.add_argument("--save", type=Path)
    ap.add_argument("--rescore", type=Path, help="recompute a saved run's fully-correct count with the current scorer, without a model")
    ap.add_argument("--show-misses", action="store_true")
    args = ap.parse_args()
    if args.rescore:
        good, n = rescore_run(json.loads(args.rescore.read_text()))
        print(f"{good}/{n} fully correct (recomputed)")
        return
    qs = [q for q in json.loads(SETS[args.qset].read_text())["questions"] if q["split"] == args.split]
    backend = OllamaChat(args.model)
    per_field: dict[str, list[bool]] = {}
    full, secs, rows = [], [], []
    for q in qs:
        t0 = time.time()
        plan = make_plan(backend, q["q"], args.planner)
        secs.append(time.time() - t0)
        ok = score(plan, q, q["q"])
        for k, v in ok.items():
            per_field.setdefault(k, []).append(v)
        full.append(all(ok.values()))
        rows.append({"q": q["q"], "ok": ok, "plan": {"in_scope": plan.in_scope, "topic": plan.topic, "kinds": plan.kinds, "area": plan.area, **plan.levels, "near_rail": plan.near_rail, "sort": plan.sort}})
        if args.show_misses and not all(ok.values()):
            print(f"MISS {q['q']!r}: wrong {[k for k, v in ok.items() if not v]} -> topic={plan.topic!r} kinds={plan.kinds} area={plan.area} "
                  f"levels={ {a: v for a, v in plan.levels.items() if v != 'any'} } rail={plan.near_rail} sort={plan.sort} in_scope={plan.in_scope}")
    print(f"\nmodel {backend.name}, split {args.split}, {len(qs)} questions, median {sorted(secs)[len(secs) // 2]:.1f} s per plan")
    for k, v in per_field.items():
        print(f"  {k:10s} {sum(v):2d}/{len(v):2d}")
    print(f"  fully correct plans: {sum(full)}/{len(full)}")
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps({"model": backend.name, "planner": args.planner, "set": args.qset, "split": args.split, "fully_correct": sum(full), "n": len(full), "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
