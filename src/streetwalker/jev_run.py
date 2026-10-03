"""Run Jev over every building.   Usage: python -m streetwalker.jev_run [--prompt p1] [--workers 6] [--resume RUN_ID]

Resumable: buildings already answered in the run are skipped, and buildings that errored are retried.
Requests run in parallel; every database write happens on the main thread. When the run completes the
answers are also stored as a baseline (`jev-<prompt>`) so evaluate.py can compare Jev with the others.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg

from streetwalker import db
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import (
    MODEL_VERSION,
    PROMPT_VERSION,
    PROMPT_VERSIONS,
    build_questions,
)
from streetwalker.jev_trial import INPUT_USD_PER_MTOK


def store_as_baseline(conn: psycopg.Connection, run_id: int, name: str) -> int:
    """Copy a run's answers into baseline_prediction: D1 arg-max with its distribution, D2, and D3 at p >= 0.5."""
    rows = conn.execute(
        """
        SELECT d1.building_id, d1.answer, d1.probs, d1.confidence, d2.answer, d3.probs->>'yes'
        FROM decision d1
        JOIN decision d2 ON d2.run_id = d1.run_id AND d2.building_id = d1.building_id AND d2.question = 'd2'
        JOIN decision d3 ON d3.run_id = d1.run_id AND d3.building_id = d1.building_id AND d3.question = 'd3'
        WHERE d1.run_id = %s AND d1.question = 'd1' AND d1.error IS NULL
        """, (run_id,)).fetchall()
    out = []
    for bid, d1, probs, conf, d2, p_food in rows:
        out.append((bid, name, d1, None if d2 == "none" else d2, float(p_food) >= 0.5, "jev",
                    json.dumps({**probs, "food": float(p_food)}), conf))
    conn.execute("DELETE FROM baseline_prediction WHERE baseline = %s", (name,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO baseline_prediction (building_id, baseline, d1_class, d2_type, d3_food, rule, probs, confidence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)", out)
    return len(out)


def run(conn: psycopg.Connection, prompt: str, workers: int, resume: int | None, limit: int | None) -> int:
    rows = conn.execute(
        "SELECT building_id, text FROM evidence WHERE tier = 0 ORDER BY building_id"
    ).fetchall()
    if limit:
        rows = rows[:limit]
    if resume:
        run_id = resume
        conn.execute("DELETE FROM decision WHERE run_id = %s AND error IS NOT NULL", (run_id,))
        done = {r[0] for r in conn.execute("SELECT DISTINCT building_id FROM decision WHERE run_id = %s", (run_id,))}
        todo = [r for r in rows if r[0] not in done]
        print(f"resuming run {run_id}: {len(done)} done, {len(todo)} to go", flush=True)
    else:
        run_id = conn.execute(
            "INSERT INTO jev_run (purpose, prompt_version, model_version, state_format, n_buildings) "
            "VALUES (%s, %s, %s, 'text', %s) RETURNING id", (f"full-{prompt}", prompt, MODEL_VERSION, len(rows)),
        ).fetchone()[0]
        todo = rows
        print(f"run {run_id}: {len(todo)} buildings, prompt {prompt}, model {MODEL_VERSION}", flush=True)
    conn.commit()

    client, questions = make_client(), build_questions(prompt)
    errors = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ask, client, text, questions): bid for bid, text in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            bid, r = futures[fut], fut.result()
            if r.error:
                errors += 1
                conn.execute(
                    "INSERT INTO decision (run_id, building_id, question, model_version, latency_ms, error) "
                    "VALUES (%s, %s, 'd1', %s, %s, %s)", (run_id, bid, MODEL_VERSION, r.latency_ms, r.error))
            for a in r.answers:
                conn.execute(
                    "INSERT INTO decision (run_id, building_id, question, answer, probs, confidence, model_version, "
                    "input_tokens, output_tokens, latency_ms) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)",
                    (run_id, bid, a.question, a.answer, json.dumps(a.probs), a.confidence,
                     r.model or MODEL_VERSION, r.input_tokens, r.output_tokens, r.latency_ms))
            if i % 100 == 0:
                conn.commit()
                print(f"  {i}/{len(todo)} done, {errors} errors", flush=True)
    conn.commit()

    tin, tout = conn.execute(
        "SELECT sum(input_tokens), sum(output_tokens) FROM (SELECT DISTINCT ON (building_id) input_tokens, output_tokens "
        "FROM decision WHERE run_id = %s AND error IS NULL ORDER BY building_id) t", (run_id,)).fetchone()
    tin, tout = tin or 0, tout or 0
    conn.execute("UPDATE jev_run SET input_tokens = %s, output_tokens = %s, est_cost_usd = %s, finished_at = now() WHERE id = %s",
                 (tin, tout, tin / 1e6 * INPUT_USD_PER_MTOK, run_id))
    conn.commit()
    print(f"run {run_id} finished: {errors} errors this pass, {tin} input tokens, est. cost ${tin / 1e6 * INPUT_USD_PER_MTOK:.3f}", flush=True)
    return run_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=PROMPT_VERSION, choices=PROMPT_VERSIONS)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", type=int, metavar="RUN_ID")
    ap.add_argument("--limit", type=int, help="only the first N buildings (testing)")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        run_id = run(conn, args.prompt, args.workers, args.resume, args.limit)
        n_missing = conn.execute(
            "SELECT count(*) FROM evidence e WHERE e.tier = 0 AND NOT EXISTS (SELECT 1 FROM decision d WHERE d.run_id = %s AND d.building_id = e.building_id AND d.question = 'd3' AND d.error IS NULL)",
            (run_id,)).fetchone()[0] if not args.limit else 0
        if n_missing:
            print(f"{n_missing} buildings have no answer yet; re-run with --resume {run_id}")
        else:
            n = store_as_baseline(conn, run_id, f"jev-{args.prompt}")
            conn.commit()
            print(f"stored {n} answers as baseline jev-{args.prompt}")


if __name__ == "__main__":
    main()
