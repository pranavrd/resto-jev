"""Run Jev aspect scoring over the reviews of linked places (decision 0020).
Usage: .venv/bin/python -u -m streetwalker.aspect_run [--limit N] [--workers 6] [--resume RUN_ID] [--sample N]

PRIVATE: sends review text to the hosted Jev API (the owner's decision, see decision 0001) and stores derived scores.
Resumable: reviews already answered in the run are skipped, errored ones are retried. Requests run in parallel; every
database write happens on the main thread.
"""

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg

from streetwalker import db
from streetwalker.aspects import ASPECT_PROMPT_VERSION, build_questions, parse_aspects
from streetwalker.jev_client import ask, make_client
from streetwalker.jev_questions import MODEL_VERSION
from streetwalker.jev_trial import INPUT_USD_PER_MTOK

MAX_CHARS = 5000  # Yelp's own cap on review length


def state_for(text: str) -> str:
    return "Restaurant review:\n" + text[:MAX_CHARS]


def run(conn: psycopg.Connection, workers: int, resume: int | None, limit: int | None, sample: int | None, purpose: str) -> int:
    rows = conn.execute("SELECT DISTINCT review_id, text FROM place_review ORDER BY review_id").fetchall()
    if sample:
        rows = random.Random(20261004).sample(rows, min(sample, len(rows)))
    if limit:
        rows = rows[:limit]
    if resume:
        run_id = resume
        conn.execute("DELETE FROM aspect_request WHERE run_id = %s AND error IS NOT NULL", (run_id,))
        done = {r[0] for r in conn.execute("SELECT review_id FROM aspect_request WHERE run_id = %s", (run_id,))}
        todo = [r for r in rows if r[0] not in done]
        print(f"resuming run {run_id}: {len(done)} done, {len(todo)} to go", flush=True)
    else:
        run_id = conn.execute(
            "INSERT INTO aspect_run (purpose, prompt_version, model_version, n_reviews) VALUES (%s, %s, %s, %s) RETURNING id",
            (purpose, ASPECT_PROMPT_VERSION, MODEL_VERSION, len(rows)),
        ).fetchone()[0]
        todo = rows
        print(f"run {run_id}: {len(todo)} reviews, prompt {ASPECT_PROMPT_VERSION}, model {MODEL_VERSION}", flush=True)
    conn.commit()

    client, questions = make_client(), build_questions()
    errors = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ask, client, state_for(text), questions): rid for rid, text in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            rid, r = futures[fut], fut.result()
            conn.execute(
                "INSERT INTO aspect_request (run_id, review_id, input_tokens, output_tokens, latency_ms, error) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (run_id, review_id) DO UPDATE SET input_tokens = EXCLUDED.input_tokens, output_tokens = EXCLUDED.output_tokens, "
                "latency_ms = EXCLUDED.latency_ms, error = EXCLUDED.error",
                (run_id, rid, r.input_tokens, r.output_tokens, r.latency_ms, r.error),
            )
            if r.error:
                errors += 1
            else:
                for a in parse_aspects({x.question: x for x in r.answers}):
                    conn.execute(
                        "INSERT INTO aspect_score (run_id, review_id, aspect, mentioned, score, confidence, probs) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) "
                        "ON CONFLICT DO NOTHING",
                        (run_id, rid, a["aspect"], a["mentioned"], a["score"], a["confidence"], json.dumps(a["probs"])),
                    )
            if i % 200 == 0:
                conn.commit()
                print(f"  {i}/{len(todo)} done, {errors} errors", flush=True)
    conn.commit()
    tin, tout = conn.execute("SELECT sum(input_tokens), sum(output_tokens) FROM aspect_request WHERE run_id = %s AND error IS NULL", (run_id,)).fetchone()
    tin, tout = tin or 0, tout or 0
    conn.execute("UPDATE aspect_run SET input_tokens = %s, output_tokens = %s, est_cost_usd = %s, finished_at = now() WHERE id = %s",
                 (tin, tout, tin / 1e6 * INPUT_USD_PER_MTOK, run_id))
    conn.commit()
    print(f"run {run_id} finished: {errors} errors this pass, {tin:,} input tokens, est. cost ${tin / 1e6 * INPUT_USD_PER_MTOK:.3f}", flush=True)
    return run_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", type=int, metavar="RUN_ID")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sample", type=int, help="a fixed random sample of N reviews (pilot)")
    ap.add_argument("--purpose", default="full")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        run(conn, args.workers, args.resume, args.limit, args.sample, args.purpose)


if __name__ == "__main__":
    main()
