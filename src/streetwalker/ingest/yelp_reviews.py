"""Load Yelp reviews for the businesses linked to census places (decision 0020). Reads the review file on stdin, so the
5 GB file never has to be written to disk:

  unzip -p ../Yelp-JSON.zip "Yelp JSON/yelp_dataset.tar" | tar -xOf - yelp_academic_dataset_review.json \\
      | .venv/bin/python -m streetwalker.ingest.yelp_reviews

PRIVATE: Yelp Data. user_id is dropped on the way in. Re-run after `ingest.yelp` (which deletes the businesses and, by
cascade, their reviews) or after a change to the links.
"""

import json
import sys
from collections.abc import Iterable

import psycopg

from streetwalker import db

BATCH = 2000


def wanted_businesses(conn: psycopg.Connection) -> set[str]:
    """Businesses behind usable links, plus duplicate listings of them."""
    rows = conn.execute("SELECT business_id FROM yelp_link_usable UNION SELECT business_id FROM yelp_alias").fetchall()
    return {r[0] for r in rows}


def keep(line: str, wanted: set[str]) -> dict | None:
    """The review as a row, or None when it is for a business we do not need. Cheap pre-check before parsing the JSON."""
    start = line.find('"business_id":"')
    if start < 0:
        return None
    bid = line[start + 15 : start + 37]  # business ids are 22 characters
    if bid not in wanted:
        return None
    r = json.loads(line)
    return {"review_id": r["review_id"], "business_id": r["business_id"], "stars": int(r["stars"]), "date": r["date"][:10], "text": r["text"],
            "useful": r["useful"], "funny": r["funny"], "cool": r["cool"]}


def ingest_reviews(conn: psycopg.Connection, lines: Iterable[str], wanted: set[str]) -> tuple[int, int]:
    """Returns (lines read, reviews kept). Replaces the stored reviews."""
    conn.execute("DELETE FROM yelp_review")
    seen = kept = 0
    batch: list[dict] = []

    def flush() -> None:
        if batch:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO yelp_review (review_id, business_id, stars, date, text, useful, funny, cool) "
                    "VALUES (%(review_id)s, %(business_id)s, %(stars)s, %(date)s, %(text)s, %(useful)s, %(funny)s, %(cool)s) ON CONFLICT DO NOTHING",
                    batch,
                )
            batch.clear()

    for line in lines:
        seen += 1
        row = keep(line, wanted)
        if row:
            batch.append(row)
            kept += 1
            if len(batch) >= BATCH:
                flush()
        if seen % 1_000_000 == 0:
            print(f"  read {seen:,} lines, kept {kept:,}", file=sys.stderr, flush=True)
    flush()
    return seen, kept


def main() -> None:
    if sys.stdin.isatty():
        raise SystemExit(__doc__)
    with db.connect() as conn:
        db.migrate(conn)
        wanted = wanted_businesses(conn)
        if not wanted:
            raise SystemExit("no linked Yelp businesses: run ingest.yelp and yelp_match first")
        seen, kept = ingest_reviews(conn, sys.stdin, wanted)
        conn.commit()
        print(f"read {seen:,} reviews, kept {kept:,} for {len(wanted)} businesses")


if __name__ == "__main__":
    main()
