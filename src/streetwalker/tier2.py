"""Tier 2 of the cascade: a local LLM reads the same evidence text Jev reads and answers D1 (decision 0018).

The model is the Qwen2.5-VL-3B already used for captions, run text-only, so nothing extra is downloaded. The prompt is
fixed in advance (TIER2_PROMPT_VERSION); results go to `tier2_result` and a run can be resumed.
Usage: .venv/bin/python -u -m streetwalker.tier2 [--tau 0.77] [--limit N]
"""

import argparse
import re
import time

from streetwalker import db
from streetwalker.cascade import load_rows
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.jev_questions import D1_CRITERIA, D1_INSTRUCTIONS
from streetwalker.vlm import MODEL_ID

TIER2_PROMPT_VERSION = "t2-p1"
ALIASES = {
    "residential": ("residential",),
    "commercial": ("commercial",),
    "mixed-use": ("mixed-use", "mixed use"),
    "industrial": ("industrial",),
    "civic-institutional": ("civic-institutional", "civic institutional", "civic", "institutional"),
    "vacant": ("vacant",),
    "other": ("other",),
}


def build_prompt(evidence: str) -> str:
    options = "\n".join(f"- {c}: {D1_CRITERIA[c]}" for c in D1_CLASSES)
    return (
        "You classify one building in Philadelphia from facts about it.\n"
        f"{D1_INSTRUCTIONS}\n\nOptions:\n{options}\n\nFacts:\n{evidence}\n\n"
        "Reply with exactly one option name from the list and nothing else."
    )


def parse_answer(text: str) -> str | None:
    """The first class named in the reply, or None when it names none."""
    low = text.lower()
    hits = [(m.start(), cls) for cls, names in ALIASES.items() for n in names for m in [re.search(rf"\b{re.escape(n)}\b", low)] if m]
    return min(hits)[1] if hits else None


def run(conn, tau: float, limit: int | None) -> None:
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config

    ids = [r.building_id for r in load_rows(conn, ("train", "dev", "test")) if r.conf < tau]
    done = {r[0] for r in conn.execute("SELECT building_id FROM tier2_result")}
    todo = [b for b in ids if b not in done][:limit]
    texts = dict(conn.execute("SELECT building_id, text FROM evidence WHERE tier = 0 AND building_id = ANY(%s)", (todo,)).fetchall())
    print(f"band {len(ids)} buildings; {len(done)} done, {len(todo)} to run", flush=True)
    model, processor = load(MODEL_ID)
    config = load_config(MODEL_ID)
    t0 = time.perf_counter()
    for i, bid in enumerate(todo, 1):
        prompt = apply_chat_template(processor, config, build_prompt(texts[bid]), num_images=0)
        t = time.perf_counter()
        out = generate(model, processor, prompt, max_tokens=12, verbose=False, temperature=0.0)
        raw = out.text.strip()
        conn.execute(
            "INSERT INTO tier2_result (building_id, model, answer, raw, seconds) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (building_id) DO UPDATE SET model = EXCLUDED.model, answer = EXCLUDED.answer, raw = EXCLUDED.raw, "
            "seconds = EXCLUDED.seconds, created_at = now()",
            (bid, f"{MODEL_ID} {TIER2_PROMPT_VERSION}", parse_answer(raw), raw, time.perf_counter() - t),
        )
        conn.commit()
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} ({(time.perf_counter() - t0) / 60:.1f} min)", flush=True)
    print(f"done in {(time.perf_counter() - t0) / 60:.1f} min", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau", type=float, default=0.77)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        run(conn, args.tau, args.limit)


if __name__ == "__main__":
    main()
