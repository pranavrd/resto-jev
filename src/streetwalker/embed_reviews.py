"""Embed the review text for dense retrieval (decision 0024).   Usage: .venv/bin/python -m streetwalker.embed_reviews [--limit N]

PRIVATE: reads Yelp review text and writes vectors derived from it to the local database. Review text goes only to the local
Ollama server. Resumable: reviews that already have a vector for the current model are skipped.
"""

import argparse
import time

from streetwalker import db
from streetwalker.embeddings import BATCH, embed, model_id, vec_literal

TODO = """
    SELECT r.review_id, r.text FROM yelp_review r
    WHERE EXISTS (SELECT 1 FROM place_review pr WHERE pr.review_id = r.review_id)
      AND NOT EXISTS (SELECT 1 FROM review_embedding e WHERE e.review_id = r.review_id AND e.model = %s)
    ORDER BY r.review_id
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="stop after this many reviews (for a trial)")
    args = ap.parse_args()
    model = model_id()
    with db.connect() as conn:
        db.migrate(conn)
        rows = conn.execute(TODO + (" LIMIT %s" if args.limit else ""), (model, args.limit) if args.limit else (model,)).fetchall()
        print(f"{model}: {len(rows):,} reviews to embed")
        t0 = time.time()
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            vecs = embed([t for _, t in chunk], "document")
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO review_embedding (review_id, model, embedding) VALUES (%s, %s, %s::vector) ON CONFLICT DO NOTHING",
                    [(rid, model, vec_literal(v)) for (rid, _), v in zip(chunk, vecs, strict=True)],
                )
            conn.commit()
            done = i + len(chunk)
            if (i // BATCH) % 50 == 0 or done == len(rows):
                rate = done / (time.time() - t0)
                print(f"  {done:,}/{len(rows):,}  {rate:.0f}/s  eta {(len(rows) - done) / rate / 60:.1f} min", flush=True)
        print(f"done: {conn.execute('SELECT count(*) FROM review_embedding WHERE model = %s', (model,)).fetchone()[0]:,} vectors stored for {model}")


if __name__ == "__main__":
    main()
