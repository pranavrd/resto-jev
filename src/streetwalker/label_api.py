"""Endpoints behind the aspect labelling page (#/label). They write labels, so api.py mounts them only when
STREETWALKER_REVIEW=1 (the same switch as the building review). Local use only: there is no login.

The page is blind on purpose: an item carries the review text and nothing else. No star rating, no place, no Jev answer.
"""

import json

from fastapi import APIRouter, HTTPException
from psycopg.rows import tuple_row
from pydantic import BaseModel, Field

from streetwalker.aspect_labels import latest_labels, valid_labels
from streetwalker.aspects import ASPECTS, DEFINITIONS, LEVELS
from streetwalker.deps import Conn

router = APIRouter(prefix="/label", tags=["label"])


class Submit(BaseModel):
    item_id: int
    labels: dict[str, int | None]
    seconds: float | None = Field(default=None, ge=0, le=7200)


@router.get("/schema")
def schema() -> dict:
    """The aspects and the five level descriptions: the same words Jev is given, so a person and Jev judge the same scale."""
    return {"aspects": [{"aspect": a, "definition": DEFINITIONS[a], "levels": LEVELS[a]} for a in ASPECTS]}


@router.get("/queue")
def queue(conn: Conn) -> dict:
    out = {}
    for r in conn.execute("SELECT batch, count(*) AS total FROM aspect_label_item GROUP BY batch ORDER BY batch").fetchall():
        done = len(latest_labels(conn, r["batch"]))
        out[str(r["batch"])] = {"total": r["total"], "labelled": done, "remaining": r["total"] - done}
    return out


@router.get("/next")
def next_item(conn: Conn, batch: int = 1) -> dict:
    done = latest_labels(conn, batch)
    items = conn.execute(
        "SELECT i.item_id, i.rank, r.text FROM aspect_label_item i LEFT JOIN yelp_review r USING (review_id) WHERE i.batch = %s ORDER BY i.rank", (batch,)
    ).fetchall()
    state = {"total": len(items), "labelled": len(done)}
    todo = next((r for r in items if r["item_id"] not in done and r["text"] is not None), None)
    if todo is None:
        return {**state, "item": None}
    return {**state, "item": {"item_id": todo["item_id"], "rank": todo["rank"], "text": todo["text"]}}


@router.post("/submit")
def submit(body: Submit, conn: Conn) -> dict:
    if not valid_labels(body.labels):
        raise HTTPException(422, "labels must name exactly food, atmosphere, service and value, each a level 0 to 4 or null for not mentioned")
    if not conn.execute("SELECT 1 FROM aspect_label_item WHERE item_id = %s", (body.item_id,)).fetchone():
        raise HTTPException(404, "no such item")
    conn.execute("INSERT INTO aspect_label (item_id, labels, seconds) VALUES (%s, %s::jsonb, %s)", (body.item_id, json.dumps(body.labels), body.seconds))
    return {"ok": True}


@router.post("/undo")
def undo(conn: Conn, batch: int = 1) -> dict:
    """Withdraw the most recent label in this batch (the row is kept, flagged undone) so the page shows that item again."""
    row = conn.cursor(row_factory=tuple_row).execute(
        "UPDATE aspect_label SET undone = true WHERE id = (SELECT max(l.id) FROM aspect_label l JOIN aspect_label_item i USING (item_id) "
        "WHERE i.batch = %s AND NOT l.undone) RETURNING item_id", (batch,)).fetchone()
    return {"undone": row[0] if row else None}
