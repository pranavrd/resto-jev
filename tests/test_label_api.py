import importlib

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from streetwalker import db
from streetwalker.aspect_labels import valid_labels
from streetwalker.aspects import ASPECTS

ALL_NONE = {a: None for a in ASPECTS}


def test_valid_labels_are_exactly_the_four_aspects_with_levels_0_to_4_or_none():
    assert valid_labels(ALL_NONE) and valid_labels({**ALL_NONE, "food": 0, "service": 4})
    assert not valid_labels({**ALL_NONE, "food": 5}) and not valid_labels({**ALL_NONE, "food": -1})
    assert not valid_labels({"food": 3})  # an aspect missing
    assert not valid_labels({**ALL_NONE, "price": 2})  # an aspect that does not exist
    assert not valid_labels({**ALL_NONE, "food": True})  # True is not a level
    assert not valid_labels({**ALL_NONE, "food": 2.5})


class _NoCommit:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ready() -> bool:
    try:
        with db.connect() as conn:
            return bool(conn.execute("SELECT count(*) FROM aspect_label_item").fetchone()[0])
    except (psycopg.Error, KeyError):
        return False


needs_db = pytest.mark.skipif(not _ready(), reason="needs the local DB with a seeded label batch (aspect_labels seed)")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STREETWALKER_REVIEW", "1")
    from streetwalker import api, deps

    importlib.reload(api)
    conn = db.connect()
    conn.row_factory = dict_row
    api.app.dependency_overrides[deps.get_conn] = lambda: _NoCommit(conn)
    conn.execute("DELETE FROM aspect_label")  # inside the transaction only: rolled back below
    yield TestClient(api.app), conn
    conn.rollback()
    conn.close()
    monkeypatch.delenv("STREETWALKER_REVIEW")
    importlib.reload(api)


@needs_db
def test_schema_gives_four_aspects_with_five_described_levels(client):
    http, _ = client
    schema = http.get("/label/schema").json()["aspects"]
    assert [a["aspect"] for a in schema] == list(ASPECTS) and all(len(a["levels"]) == 5 and a["definition"] for a in schema)


@needs_db
def test_the_item_is_blind_review_text_and_nothing_else(client):
    http, _ = client
    item = http.get("/label/next").json()["item"]
    assert set(item) == {"item_id", "rank", "text"} and item["text"]
    assert not any(k in item for k in ("stars", "place", "place_id", "stratum", "aspects", "jev", "business_id", "user_id"))


@needs_db
def test_submit_next_and_undo(client):
    http, _ = client
    first = http.get("/label/next").json()
    assert first["labelled"] == 0 and first["total"] >= 100
    one = first["item"]["item_id"]
    ok = http.post("/label/submit", json={"item_id": one, "labels": {**ALL_NONE, "food": 4}, "seconds": 31.5})
    assert ok.status_code == 200
    second = http.get("/label/next").json()
    assert second["labelled"] == 1 and second["item"]["item_id"] != one
    assert http.post("/label/undo").json() == {"undone": one}
    again = http.get("/label/next").json()
    assert again["labelled"] == 0 and again["item"]["item_id"] == one


@needs_db
def test_bad_submissions_are_refused(client):
    http, _ = client
    one = http.get("/label/next").json()["item"]["item_id"]
    for labels in ({"food": 3}, {**ALL_NONE, "food": 5}, {**ALL_NONE, "taste": 2}):
        assert http.post("/label/submit", json={"item_id": one, "labels": labels}).status_code == 422
    assert http.post("/label/submit", json={"item_id": -1, "labels": ALL_NONE}).status_code == 404
    assert http.post("/label/submit", json={"item_id": one, "labels": ALL_NONE, "seconds": -3}).status_code == 422


@needs_db
def test_a_repeat_is_its_own_item_and_the_latest_label_counts(client):
    http, conn = client
    rep = conn.execute("SELECT item_id, repeat_of FROM aspect_label_item WHERE repeat_of IS NOT NULL LIMIT 1").fetchone()
    assert rep is not None and rep["repeat_of"] != rep["item_id"]
    for level in (1, 3):
        http.post("/label/submit", json={"item_id": rep["item_id"], "labels": {**ALL_NONE, "food": level}})
    from streetwalker.aspect_labels import latest_labels

    assert latest_labels(conn, 1)[rep["item_id"]]["food"] == 3


@needs_db
def test_deleting_a_review_never_deletes_the_labels(client):
    http, conn = client
    item = conn.execute("SELECT item_id, review_id FROM aspect_label_item WHERE batch = 1 ORDER BY rank LIMIT 1").fetchone()
    http.post("/label/submit", json={"item_id": item["item_id"], "labels": {**ALL_NONE, "service": 2}})
    conn.execute("DELETE FROM yelp_review WHERE review_id = %s", (item["review_id"],))  # what a relink does to an unusable business
    assert conn.execute("SELECT count(*) AS n FROM aspect_label WHERE item_id = %s", (item["item_id"],)).fetchone()["n"] == 1
    # the item cannot be shown without its review, and the page moves on
    assert http.get("/label/next").json()["item"]["item_id"] != item["item_id"]
