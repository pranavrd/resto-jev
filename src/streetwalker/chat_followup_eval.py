"""Evaluate multi-turn follow-ups (decision 0031).   Usage: .venv/bin/python -m streetwalker.chat_followup_eval --split dev|test [--show-misses] [--save FILE]

For each invented conversation the follow-up message is rewritten with its history (`chat.rewrite_question`), the rewrite is planned (`chat.make_plan`, planner p2)
and the plan is scored against the plan expected for the question the message means (the scorer of the planner sets). The baseline is the same planner on the
bare message with no history. Controls (messages that are NOT follow-ups) must come back unchanged.

Develop on `dev`; `--split test` is read once and logged in docs/chat-eval/log.md. The conversations are invented: no Yelp data.
"""

import argparse
import json
from pathlib import Path

from streetwalker.chat import PLAN_VERSION, OllamaChat, Turn, make_plan, rewrite_question
from streetwalker.chat_eval import EVAL_DIR, score

FOLLOWUP_SETS = {"v1": EVAL_DIR / "followups_v1.json", "v2": EVAL_DIR / "followups_v2.json", "v3": EVAL_DIR / "followups_v3.json"}  # v2: decision 0032
FOLLOWUPS = FOLLOWUP_SETS["v1"]


def evaluate(backend, split: str, planner: str = PLAN_VERSION, qset: str = "v1", rewrite=rewrite_question) -> list[dict]:
    rows = []
    for c in (x for x in json.loads(FOLLOWUP_SETS[qset].read_text())["conversations"] if x["split"] == split):
        history = [Turn(**t) for t in c["history"]]
        standalone, followup = rewrite(backend, c["message"], history)
        if c.get("score_plan", True):
            with_history = score(make_plan(backend, standalone, planner), c, standalone)
            without = score(make_plan(backend, c["message"], planner), c, c["message"])
        else:  # a complete question: what is judged is that it came back unchanged; the planner has its own sets
            with_history = without = {"unchanged": standalone == " ".join(c["message"].split())}
        control = c["followup_ok"] == [False]
        rows.append({
            "kind": c.get("kind", ""), "message": c["message"], "standalone": standalone, "followup": followup, "followup_ok": followup in c["followup_ok"], "control": control,
            "unchanged": standalone == " ".join(c["message"].split()), "plan_ok": all(with_history.values()), "wrong": [k for k, v in with_history.items() if not v],
            "baseline_plan_ok": all(without.values()),
        })
    return rows


def rewrite_for(version: str):
    """The rewrite function of a version. r1 is the one of decision 0031; r2 is added by decision 0032 once it exists."""
    from streetwalker import chat

    return lambda backend, message, history: chat.rewrite_question(backend, message, history, version)


def summarise(rows: list[dict]) -> dict:
    controls = [r for r in rows if r["control"]]
    return {
        "n": len(rows),
        "with_history_fully_correct": sum(r["plan_ok"] and r["followup_ok"] for r in rows),
        "plan_correct": sum(r["plan_ok"] for r in rows),
        "baseline_plan_correct": sum(r["baseline_plan_ok"] for r in rows),
        "followup_flag_ok": sum(r["followup_ok"] for r in rows),
        "controls": len(controls), "controls_unchanged": sum(r["unchanged"] for r in controls),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--model")
    ap.add_argument("--set", choices=list(FOLLOWUP_SETS), default="v1", dest="qset")
    ap.add_argument("--rewrite", choices=["r1", "r2", "r3"], default="r1", help="the follow-up rewrite version (r1: decision 0031; r2, r3: decision 0032)")
    ap.add_argument("--planner", default=PLAN_VERSION)
    ap.add_argument("--show-misses", action="store_true")
    ap.add_argument("--save", type=Path)
    args = ap.parse_args()
    backend = OllamaChat(args.model)
    rows = evaluate(backend, args.split, args.planner, args.qset, rewrite_for(args.rewrite))
    for r in rows:
        if args.show_misses and not (r["plan_ok"] and r["followup_ok"]):
            print(f"MISS {r['message']!r} -> {r['standalone']!r} (followup={r['followup']}, flag ok {r['followup_ok']}, wrong {r['wrong']})")
    s = summarise(rows)
    for kind in sorted({r["kind"] for r in rows if r["kind"]}):
        sub = [r for r in rows if r["kind"] == kind]
        print(f"  {kind:11s} {sum(r['plan_ok'] and r['followup_ok'] for r in sub)}/{len(sub)} fully correct; baseline plan {sum(r['baseline_plan_ok'] for r in sub)}/{len(sub)}")
    print(f"\nmodel {backend.name}, planner {args.planner}, rewrite {args.rewrite}, set {args.qset}, split {args.split}, {s['n']} conversations")
    print(f"  rewrite + plan fully correct (plan and follow-up flag): {s['with_history_fully_correct']}/{s['n']}")
    print(f"  plan correct with history {s['plan_correct']}/{s['n']}, without history (baseline) {s['baseline_plan_correct']}/{s['n']}")
    print(f"  follow-up flag acceptable: {s['followup_flag_ok']}/{s['n']}; controls returned unchanged: {s['controls_unchanged']}/{s['controls']}")
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps({"model": backend.name, "planner": args.planner, "rewrite": args.rewrite, "set": args.qset, "split": args.split, "summary": s, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
