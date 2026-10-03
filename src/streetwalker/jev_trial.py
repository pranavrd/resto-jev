"""Small Jev trial on a stratified sample of train buildings.

Usage:
  python -m streetwalker.jev_trial                      # dry run: show the sample and one request, no API calls
  python -m streetwalker.jev_trial --run                # make the calls (about 100 requests)
  python -m streetwalker.jev_trial --report RUN_ID      # analyse a stored run

The sample comes from the train split only, so question wording can be iterated without touching dev or
test. It is deliberately not representative (hard cases are over-sampled), so accuracy is not comparable
with the baselines' natural-prevalence accuracy; compare per class and on the same buildings.
"""

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass

import psycopg

from streetwalker import db
from streetwalker.calibration import ece, reliability_bins
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import (
    MODEL_VERSION,
    PROMPT_VERSION,
    PROMPT_VERSIONS,
    build_questions,
)
from streetwalker.metrics import accuracy, binary, confusion, per_class

INPUT_USD_PER_MTOK = 0.042  # TypeSafe list price for jev-1.13 input tokens; output is free
SET_NAME = "jev-trial-1"
SEED = 0


@dataclass(frozen=True)
class Cand:
    building_id: int
    d1: str
    d3_food: bool
    highway: str


STRATA = [
    ("food_licensed", 15, lambda c: c.d3_food),
    ("commercial", 15, lambda c: c.d1 == "commercial"),
    ("mixed-use", 20, lambda c: c.d1 == "mixed-use"),
    ("residential_corridor", 10, lambda c: c.d1 == "residential" and c.highway in ("primary", "tertiary")),
    ("residential", 24, lambda c: c.d1 == "residential"),
    ("civic-institutional", 8, lambda c: c.d1 == "civic-institutional"),
    ("industrial", 3, lambda c: c.d1 == "industrial"),
    ("other", 4, lambda c: c.d1 == "other"),
    ("vacant", 1, lambda c: c.d1 == "vacant"),
]


def sample_trial(cands: list[Cand], seed: int = SEED) -> list[tuple[Cand, str]]:
    """Each building is used once; strata are filled in order, so food-licensed buildings come first."""
    rng = random.Random(seed)
    taken: set[int] = set()
    out = []
    for name, n, pred in STRATA:
        pool = sorted((c for c in cands if pred(c) and c.building_id not in taken), key=lambda c: c.building_id)
        for c in rng.sample(pool, min(n, len(pool))):
            taken.add(c.building_id)
            out.append((c, name))
    return out


def load_candidates(conn: psycopg.Connection) -> tuple[list[Cand], dict[int, str]]:
    rows = conn.execute(
        "SELECT g.building_id, g.d1_class, g.d3_food, e.payload->'street'->>'highway', e.text "
        "FROM ground_truth g JOIN evidence e ON e.building_id = g.building_id AND e.tier = 0 "
        "WHERE g.split = 'train' ORDER BY g.building_id"
    ).fetchall()
    return [Cand(r[0], r[1], r[2], r[3]) for r in rows], {r[0]: r[4] for r in rows}


def run(conn: psycopg.Connection, purpose: str, prompt: str) -> int:
    cands, texts = load_candidates(conn)
    sample = sample_trial(cands)
    conn.execute("DELETE FROM eval_set WHERE name = %s", (SET_NAME,))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO eval_set (name, building_id, stratum) VALUES (%s, %s, %s)",
                        [(SET_NAME, c.building_id, s) for c, s in sample])
    run_id = conn.execute(
        "INSERT INTO jev_run (purpose, prompt_version, model_version, state_format, n_buildings) "
        "VALUES (%s, %s, %s, 'text', %s) RETURNING id", (purpose, prompt, MODEL_VERSION, len(sample)),
    ).fetchone()[0]
    conn.commit()

    client = make_client()
    questions = build_questions(prompt)
    tin = tout = errors = 0
    for i, (c, _stratum) in enumerate(sample, 1):
        r = ask(client, texts[c.building_id], questions)
        tin += r.input_tokens or 0
        tout += r.output_tokens or 0
        if r.error:
            errors += 1
            conn.execute(
                "INSERT INTO decision (run_id, building_id, question, model_version, latency_ms, error) VALUES (%s,%s,'d1',%s,%s,%s)",
                (run_id, c.building_id, MODEL_VERSION, r.latency_ms, r.error))
        for a in r.answers:
            conn.execute(
                "INSERT INTO decision (run_id, building_id, question, answer, probs, confidence, model_version, "
                "input_tokens, output_tokens, latency_ms) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)",
                (run_id, c.building_id, a.question, a.answer, json.dumps(a.probs), a.confidence,
                 r.model or MODEL_VERSION, r.input_tokens, r.output_tokens, r.latency_ms))
        if i % 25 == 0:
            conn.commit()
            print(f"  {i}/{len(sample)} done", flush=True)
    conn.execute(
        "UPDATE jev_run SET input_tokens = %s, output_tokens = %s, est_cost_usd = %s, finished_at = now() WHERE id = %s",
        (tin, tout, tin / 1e6 * INPUT_USD_PER_MTOK, run_id))
    conn.commit()
    print(f"run {run_id}: {len(sample)} requests, {errors} errors, {tin} input tokens, est. cost ${tin / 1e6 * INPUT_USD_PER_MTOK:.5f}")
    return run_id


def report(conn: psycopg.Connection, run_id: int) -> None:
    rows = conn.execute(
        """
        SELECT g.building_id, g.d1_class, g.d3_food, s.stratum,
               d1.answer, d1.confidence, d1.probs, d3.probs->>'yes', d2.answer, d1.latency_ms,
               r3.d1_class, gf.d1_class
        FROM decision d1
        JOIN decision d3 ON d3.run_id = d1.run_id AND d3.building_id = d1.building_id AND d3.question = 'd3'
        JOIN decision d2 ON d2.run_id = d1.run_id AND d2.building_id = d1.building_id AND d2.question = 'd2'
        JOIN ground_truth g ON g.building_id = d1.building_id
        JOIN eval_set s ON s.name = %s AND s.building_id = d1.building_id
        JOIN baseline_prediction r3 ON r3.building_id = d1.building_id AND r3.baseline = 'rules-v3'
        JOIN baseline_prediction gf ON gf.building_id = d1.building_id AND gf.baseline = 'gbm-full'
        WHERE d1.run_id = %s AND d1.question = 'd1' AND d1.error IS NULL ORDER BY g.building_id
        """, (SET_NAME, run_id)).fetchall()
    run_row = conn.execute("SELECT prompt_version, model_version, input_tokens, output_tokens, est_cost_usd FROM jev_run WHERE id = %s", (run_id,)).fetchone()
    n_err = conn.execute("SELECT count(*) FROM decision WHERE run_id = %s AND error IS NOT NULL", (run_id,)).fetchone()[0]
    truth, pred, conf = [r[1] for r in rows], [r[4] for r in rows], [r[5] for r in rows]
    print(f"run {run_id}  prompt={run_row[0]}  model={run_row[1]}  answered={len(rows)}  errors={n_err}")
    print(f"tokens in/out {run_row[2]}/{run_row[3]}  (~{run_row[2] / max(len(rows), 1):.0f} in per request)  est. cost ${run_row[4]:.5f}")
    lat = sorted(r[9] for r in rows)
    print(f"latency ms: median {lat[len(lat) // 2]}, p90 {lat[int(len(lat) * 0.9)]}, max {lat[-1]}")

    print(f"\nJev D1 on the trial sample (NOT natural prevalence): accuracy {accuracy(truth, pred):.3f}")
    print(f"  {'class':20s} {'true':>5s} {'pred':>5s}   {'P':>5s} {'R':>5s} {'F1':>5s}")
    for s in per_class(truth, pred, list(D1_CLASSES)):
        print(f"  {s.label:20s} {s.support:5d} {s.predicted:5d}   {s.precision:5.2f} {s.recall:5.2f} {s.f1:5.2f}")
    cm = confusion(truth, pred)
    short = {c: c[:5] for c in D1_CLASSES}
    print("  confusion (rows = truth)           " + " ".join(f"{short[c]:>6s}" for c in D1_CLASSES))
    for t in D1_CLASSES:
        if any(cm[(t, p)] for p in D1_CLASSES):
            print(f"  {t:30s} " + " ".join(f"{cm[(t, p)]:6d}" for p in D1_CLASSES))

    comm = {"commercial", "mixed-use"}
    print("\ncommercial-any / food on the same 100 buildings:")
    print(f"  {'':12s} {'comm-any P':>10s} {'R':>5s} {'F1':>5s} | {'D1 acc':>7s}")
    for name, p in (("jev", pred), ("rules-v3", [r[10] for r in rows]), ("gbm-full", [r[11] for r in rows])):
        b = binary([t in comm for t in truth], [x in comm for x in p])
        print(f"  {name:12s} {b.precision:10.2f} {b.recall:5.2f} {b.f1:5.2f} | {accuracy(truth, p):7.3f}")
    food_truth = [r[2] for r in rows]
    food_p = [float(r[7]) for r in rows]
    for tau in (0.3, 0.5, 0.7):
        b = binary(food_truth, [x >= tau for x in food_p])
        print(f"  D3 food (Jev p(yes) >= {tau}): P {b.precision:.2f} R {b.recall:.2f} F1 {b.f1:.2f}  (n_true={b.support})")

    print("\nD1 calibration (Jev's confidence vs accuracy):")
    correct = [t == p for t, p in zip(truth, pred, strict=True)]
    for b in reliability_bins(conf, correct, 5):
        print(f"  conf {b.lo:.1f}-{b.hi:.1f}: n={b.n:3d}  mean conf {b.mean_confidence:.2f}  accuracy {b.accuracy:.2f}")
    print(f"  ECE {ece(conf, correct, 5):.3f} (n={len(rows)}, noisy)")

    print("\nper stratum (D1 accuracy, mean confidence):")
    for st in dict.fromkeys(r[3] for r in rows):
        sub = [r for r in rows if r[3] == st]
        print(f"  {st:22s} n={len(sub):3d}  acc {sum(r[1] == r[4] for r in sub) / len(sub):.2f}  conf {sum(r[5] for r in sub) / len(sub):.2f}")
    d2 = Counter(r[8] for r in rows if r[4] in comm and r[2])
    print("\nD2 type for food-licensed buildings Jev calls commercial/mixed:", dict(d2))


def dry_run(conn: psycopg.Connection) -> None:
    cands, texts = load_candidates(conn)
    sample = sample_trial(cands)
    print(f"trial sample: {len(sample)} train buildings")
    for name, n, _ in STRATA:
        got = sum(1 for _, s in sample if s == name)
        print(f"  {name:22s} {got:3d} / {n}")
    first = next((c for c, s in sample if s == "mixed-use"), sample[0][0])
    text = texts[first.building_id]
    print("\n--- example state (what Jev is shown) ---\n" + text)
    qs = build_questions()
    print("\n--- questions ---")
    for k, q in qs.items():
        print(f"{k}: {q.instructions}")
        print("   options:", list(q.criteria))
    approx = sum(len(texts[c.building_id]) for c, _ in sample) / 4 + len(json.dumps({k: v.model_dump() for k, v in qs.items()})) / 4 * len(sample)
    print(f"\nrough input size: ~{approx / len(sample):.0f} tokens per request, ~{approx:.0f} total, "
          f"~${approx / 1e6 * INPUT_USD_PER_MTOK:.4f} at ${INPUT_USD_PER_MTOK}/M tokens")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", type=int, metavar="RUN_ID")
    ap.add_argument("--prompt", default=PROMPT_VERSION, choices=PROMPT_VERSIONS)
    ap.add_argument("--purpose", help="label for the run; default trial-<prompt>")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        if args.report:
            report(conn, args.report)
        elif args.run:
            report(conn, run(conn, args.purpose or f"trial-{args.prompt}", args.prompt))
        else:
            dry_run(conn)


if __name__ == "__main__":
    main()
