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
from streetwalker.chat import OllamaChat, make_plan

QUESTIONS = Path(__file__).resolve().parents[2] / "docs" / "chat-eval" / "plan_questions.json"


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
        ok["topic"] = any(k in topic for k in exp["topic_any"]) and words <= 8 and topic != question.lower().rstrip("?")
    elif exp["topic_empty"]:
        ok["topic"] = topic == ""
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--show-misses", action="store_true")
    args = ap.parse_args()
    qs = [q for q in json.loads(QUESTIONS.read_text())["questions"] if q["split"] == args.split]
    backend = OllamaChat(args.model)
    per_field: dict[str, list[bool]] = {}
    full, secs = [], []
    for q in qs:
        t0 = time.time()
        plan = make_plan(backend, q["q"])
        secs.append(time.time() - t0)
        ok = score(plan, q, q["q"])
        for k, v in ok.items():
            per_field.setdefault(k, []).append(v)
        full.append(all(ok.values()))
        if args.show_misses and not all(ok.values()):
            print(f"MISS {q['q']!r}: wrong {[k for k, v in ok.items() if not v]} -> topic={plan.topic!r} kinds={plan.kinds} area={plan.area} "
                  f"levels={ {a: v for a, v in plan.levels.items() if v != 'any'} } rail={plan.near_rail} sort={plan.sort} in_scope={plan.in_scope}")
    print(f"\nmodel {backend.name}, split {args.split}, {len(qs)} questions, median {sorted(secs)[len(secs) // 2]:.1f} s per plan")
    for k, v in per_field.items():
        print(f"  {k:10s} {sum(v):2d}/{len(v):2d}")
    print(f"  fully correct plans: {sum(full)}/{len(full)}")


if __name__ == "__main__":
    main()
