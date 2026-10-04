"""Endpoints behind the review page (#/review). They write labels, so api.py mounts them only when
STREETWALKER_REVIEW=1:   STREETWALKER_REVIEW=1 .venv/bin/uvicorn streetwalker.api:app --port 8000

Nothing here returns ground truth or a model prediction, so labelling stays blind. Local use only: there is no login.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from streetwalker.deps import Conn
from streetwalker.groundtruth import D1_CLASSES
from streetwalker.images_cache import CACHE
from streetwalker.jev_questions import D1_CRITERIA
from streetwalker.review import CANT_TELL, SETS, building_view, latest_labels, valid_label
from streetwalker.tier1 import CROPS

router = APIRouter(prefix="/review", tags=["review"])
SetName = Literal["verify", "gate"]
assert set(SETS) == {"verify", "gate"}


class LabelIn(BaseModel):
    building_id: int
    set_name: SetName
    label: str
    seconds: float | None = Field(default=None, ge=0, le=3600)
    evidence_shown: bool = False


def _crop_path(conn, building_id: int) -> str | None:
    row = conn.execute("SELECT image_id FROM pano_pick WHERE building_id = %s", (building_id,)).fetchone()
    if not row:
        return None
    found = sorted(CROPS.glob(f"b{building_id}_{row['image_id']}_fov*.jpg"))
    return str(found[0]) if found else None


def _photo_path(conn, building_id: int) -> str | None:
    row = conn.execute("SELECT image_id FROM image_pick WHERE building_id = %s", (building_id,)).fetchone()
    if not row:
        return None
    path = CACHE / f"{row['image_id']}_1024.jpg"
    return str(path) if path.exists() else None


@router.get("/classes")
def classes() -> list[dict]:
    """The class definitions the reviewer sees: the same wording Jev is given."""
    return [{"label": c, "criteria": D1_CRITERIA[c]} for c in D1_CLASSES] + [
        {"label": CANT_TELL, "criteria": "You cannot tell from what is shown. This is a valid answer and is never counted as wrong."}
    ]


@router.get("/queue")
def queue(conn: Conn) -> dict:
    out = {}
    for name in SETS:
        ids = [r["building_id"] for r in conn.execute("SELECT building_id FROM review_item WHERE set_name = %s", (name,))]
        done = len(set(ids) & set(latest_labels(conn, name)))
        out[name] = {"total": len(ids), "labelled": done, "remaining": len(ids) - done}
    return out


@router.get("/next")
def next_item(conn: Conn, set_name: SetName) -> dict:
    done = set(latest_labels(conn, set_name))
    items = conn.execute("SELECT building_id, rank FROM review_item WHERE set_name = %s ORDER BY rank", (set_name,)).fetchall()
    todo = next((r for r in items if r["building_id"] not in done), None)
    state = {"total": len(items), "labelled": len(done & {r["building_id"] for r in items})}
    if todo is None:
        return {**state, "item": None}
    bid = todo["building_id"]
    view = building_view(conn, bid)
    photo_year = next((c["year"] for c in view["cameras"]), None)
    images = []
    if _photo_path(conn, bid):
        images.append({"kind": "photo", "url": f"/api/review/image/{bid}/photo", "year": photo_year})
    if _crop_path(conn, bid):
        images.append({"kind": "crop", "url": f"/api/review/image/{bid}/crop", "year": 2026})
    text = view["text"] or ""
    return {**state, "item": {
        "building_id": bid, "rank": todo["rank"], "address": text.splitlines()[0] if text else "", "evidence": text,
        "target": view["target"], "neighbours": view["neighbours"], "streets": view["streets"], "cameras": view["cameras"],
        "images": images,
    }}


@router.post("/label")
def label(body: LabelIn, conn: Conn) -> dict:
    if not valid_label(body.label):
        raise HTTPException(422, f"label must be one of {', '.join([*D1_CLASSES, CANT_TELL])}")
    if not conn.execute("SELECT 1 FROM review_item WHERE set_name = %s AND building_id = %s", (body.set_name, body.building_id)).fetchone():
        raise HTTPException(404, "that building is not in this queue")
    conn.execute(
        "INSERT INTO human_label (building_id, set_name, label, seconds, evidence_shown) VALUES (%s, %s, %s, %s, %s)",
        (body.building_id, body.set_name, body.label, body.seconds, body.evidence_shown),
    )
    return {"ok": True}


@router.post("/undo")
def undo(conn: Conn, set_name: SetName) -> dict:
    """Withdraw the most recent label in this set (the row is kept, flagged undone), so the page can show it again."""
    row = conn.execute(
        "UPDATE human_label SET undone = true WHERE id = (SELECT max(id) FROM human_label WHERE set_name = %s AND NOT undone) RETURNING building_id",
        (set_name,),
    ).fetchone()
    return {"undone": row["building_id"] if row else None}


@router.get("/image/{building_id}/{kind}")
def image(building_id: int, kind: Literal["photo", "crop"], conn: Conn) -> FileResponse:
    """Serves only a file the database says belongs to this building, from the local cache."""
    if not conn.execute("SELECT 1 FROM review_item WHERE building_id = %s LIMIT 1", (building_id,)).fetchone():
        raise HTTPException(404, "not in a review queue")
    path = _photo_path(conn, building_id) if kind == "photo" else _crop_path(conn, building_id)
    if not path:
        raise HTTPException(404, "no such image")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
