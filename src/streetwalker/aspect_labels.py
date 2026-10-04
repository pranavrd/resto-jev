"""The human labelling set for aspect scoring (decision 0021): sampling, seeding and status.
Usage: .venv/bin/python -m streetwalker.aspect_labels seed [--batch 1] [--force] | status

PRIVATE: reads review text and Jev aspect scores. The page that shows these items never shows the star rating, the place
or any Jev output, so a label cannot be anchored by them.

Batch 1 (about 180 items) is built to test the two open questions first:
  random            stratified by star rating and spread across places: an unbiased read on how well Jev agrees with a person
  value_probe       reviews Jev says mention value (only about a quarter do, so a random draw would leave too few to judge it)
  divergence_probe  reviews where Jev's aspect score and the star rating disagree: where a halo (overall tone leaking into the
                    aspects) would show
  repeat            a second showing of random items, to measure how consistent the labeller is with themself
The two probes are picked using Jev's own output, so they say how Jev does on those reviews and must be reported apart
from the random part, never pooled with it.
"""

import argparse
import random
from collections import Counter

from psycopg.rows import tuple_row

from streetwalker import db
from streetwalker.aspects import ASPECTS

MIN_CHARS = 60  # shorter reviews rarely say anything about an aspect
PER_STAR = 24  # random part: 24 reviews at each of 5 star ratings
PROBE_VALUE_PER_STAR = 5
PROBE_DIVERGENT = 20
N_REPEAT = 15
PLACE_CAP = 4  # at most this many items from one place in the batch
REPEAT_GAP = 40  # a repeat comes at least this many items after its original
SEED = 20261005
MENTION = 0.5


def valid_labels(labels: dict) -> bool:
    """Exactly the four aspects, each a level from 0 to 4 or None for not mentioned. Booleans are not levels."""
    return set(labels) == set(ASPECTS) and all(v is None or (isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 4) for v in labels.values())


def latest_labels(conn, batch: int) -> dict[int, dict]:
    """The current label of each item: the newest one that was not undone."""
    rows = conn.cursor(row_factory=tuple_row).execute(
        "SELECT DISTINCT ON (l.item_id) l.item_id, l.labels FROM aspect_label l JOIN aspect_label_item i USING (item_id) "
        "WHERE i.batch = %s AND NOT l.undone ORDER BY l.item_id, l.id DESC", (batch,)).fetchall()
    return {r[0]: r[1] for r in rows}


def divergent(c: dict) -> bool:
    """A mentioned aspect whose score disagrees with the stars: a 4 or 5 star review with a negative aspect (score <= 1.5),
    or a 1 or 2 star review with a positive one (score >= 2.5)."""
    for a in ASPECTS:
        m, s = c["aspects"].get(a, (0.0, 2.0))
        if m >= MENTION and ((c["stars"] >= 4 and s <= 1.5) or (c["stars"] <= 2 and s >= 2.5)):
            return True
    return False


def _take(pool: list[dict], n: int, used_places: Counter, rng: random.Random, taken: set[str]) -> list[dict]:
    """n reviews from the pool in random order, at most PLACE_CAP per place across the whole batch."""
    pool = [c for c in pool if c["review_id"] not in taken]
    rng.shuffle(pool)
    out = []
    for c in pool:
        if len(out) == n:
            break
        if used_places[c["place_id"]] < PLACE_CAP:
            used_places[c["place_id"]] += 1
            taken.add(c["review_id"])
            out.append(c)
    return out


def sample_batch(cands: list[dict], seed: int = SEED) -> list[dict]:
    """The items of one batch in the order they are shown: dicts with review_id, stratum and repeat_of (an index into the list).
    `cands` rows: review_id, place_id, stars, chars, aspects {name: (mentioned probability, score)}."""
    rng = random.Random(seed)
    eligible = sorted((c for c in cands if c["chars"] >= MIN_CHARS), key=lambda c: c["review_id"])
    used, taken = Counter(), set()
    items: list[dict] = []
    for stars in range(1, 6):
        for c in _take([c for c in eligible if c["stars"] == stars], PER_STAR, used, rng, taken):
            items.append({"review_id": c["review_id"], "stratum": "random"})
    for stars in range(1, 6):
        pool = [c for c in eligible if c["stars"] == stars and c["aspects"].get("value", (0.0, 2.0))[0] >= MENTION]
        for c in _take(pool, PROBE_VALUE_PER_STAR, used, rng, taken):
            items.append({"review_id": c["review_id"], "stratum": "value_probe"})
    high = [c for c in eligible if c["stars"] >= 4 and divergent(c)]
    low = [c for c in eligible if c["stars"] <= 2 and divergent(c)]
    for pool, n in ((high, PROBE_DIVERGENT // 2), (low, PROBE_DIVERGENT - PROBE_DIVERGENT // 2)):
        for c in _take(pool, n, used, rng, taken):
            items.append({"review_id": c["review_id"], "stratum": "divergence_probe"})
    rng.shuffle(items)
    # repeat only items that leave room for the gap after them
    originals = [it for k, it in enumerate(items) if it["stratum"] == "random" and k <= len(items) - REPEAT_GAP - 1]
    repeats = [{"review_id": o["review_id"], "stratum": "repeat"} for o in rng.sample(originals, min(N_REPEAT, len(originals)))]

    def index_of_original(review_id: str) -> int:
        return next(k for k, it in enumerate(items) if it["review_id"] == review_id and it["stratum"] != "repeat")

    # a repeat goes back at least REPEAT_GAP items after its original, otherwise it would be recalled rather than relabelled
    for r in sorted(repeats, key=lambda r: index_of_original(r["review_id"])):
        items.insert(min(len(items), index_of_original(r["review_id"]) + REPEAT_GAP + rng.randrange(0, 30)), r)
    return [{"review_id": it["review_id"], "stratum": it["stratum"],
             "repeat_of": index_of_original(it["review_id"]) if it["stratum"] == "repeat" else None} for it in items]


def load_candidates(conn, run_id: int) -> list[dict]:
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT r.review_id, pr.place_id, r.stars, length(r.text), s.aspect, s.mentioned, s.score
        FROM yelp_review r
        JOIN (SELECT DISTINCT ON (review_id) review_id, place_id FROM place_review ORDER BY review_id, place_id) pr USING (review_id)
        JOIN aspect_score s ON s.review_id = r.review_id AND s.run_id = %s
        """,
        (run_id,),
    ).fetchall()
    by: dict[str, dict] = {}
    for rid, pid, stars, chars, aspect, m, sc in rows:
        c = by.setdefault(rid, {"review_id": rid, "place_id": pid, "stars": stars, "chars": chars, "aspects": {}})
        c["aspects"][aspect] = (m, sc)
    return list(by.values())


def seed(conn, batch: int, force: bool) -> None:
    labelled = conn.execute(
        "SELECT count(*) FROM aspect_label l JOIN aspect_label_item i USING (item_id) WHERE i.batch = %s AND NOT l.undone", (batch,)
    ).fetchone()[0]
    if labelled and not force:
        raise SystemExit(f"batch {batch} already has {labelled} labels; re-seeding would orphan them. Use --force only if you mean it.")
    run_id = conn.execute("SELECT max(id) FROM aspect_run WHERE finished_at IS NOT NULL AND purpose LIKE 'full%'").fetchone()[0]
    items = sample_batch(load_candidates(conn, run_id), SEED + batch)
    conn.execute("DELETE FROM aspect_label WHERE item_id IN (SELECT item_id FROM aspect_label_item WHERE batch = %s)", (batch,))
    conn.execute("UPDATE aspect_label_item SET repeat_of = NULL WHERE batch = %s", (batch,))
    conn.execute("DELETE FROM aspect_label_item WHERE batch = %s", (batch,))
    ids: list[int] = []
    for rank, it in enumerate(items, 1):
        of = ids[it["repeat_of"]] if it["repeat_of"] is not None else None
        ids.append(conn.execute(
            "INSERT INTO aspect_label_item (review_id, batch, stratum, rank, repeat_of) VALUES (%s, %s, %s, %s, %s) RETURNING item_id",
            (it["review_id"], batch, it["stratum"], rank, of)).fetchone()[0])
    conn.commit()
    print(f"batch {batch}: {len(items)} items " + ", ".join(f"{k} {v}" for k, v in Counter(i['stratum'] for i in items).items()))


def status(conn) -> None:
    rows = conn.execute(
        "SELECT i.batch, count(*), count(DISTINCT i.item_id) FILTER (WHERE l.id IS NOT NULL AND NOT l.undone) "
        "FROM aspect_label_item i LEFT JOIN aspect_label l USING (item_id) GROUP BY 1 ORDER BY 1").fetchall()
    for batch, n, done in rows:
        print(f"batch {batch}: {done} of {n} labelled")
    if not rows:
        print("no batches yet")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--batch", type=int, default=1)
    s.add_argument("--force", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args()
    with db.connect() as conn:
        db.migrate(conn)
        if args.cmd == "seed":
            seed(conn, args.batch, args.force)
        else:
            status(conn)


if __name__ == "__main__":
    main()
