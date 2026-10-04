import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from streetwalker import db
from streetwalker.metrics import cohens_kappa
from streetwalker.review import CANT_TELL, LABELS, sample_verify, valid_label


def test_sample_is_deterministic_capped_per_area_and_balanced_by_prefix():
    cands = [(i, "a") for i in range(100)] + [(1000 + i, "b") for i in range(100)] + [(2000 + i, "c") for i in range(7)]
    one, two = sample_verify(cands, 10), sample_verify(cands, 10)
    assert one == two and len(set(one)) == len(one) == 27  # area c has only 7
    area = {b: a for b, a in cands}
    assert [area[b] for b in one[:6]] == ["a", "b", "c", "a", "b", "c"]  # round-robin, so any prefix is balanced
    assert sample_verify(cands, 10, seed=1) != one


def test_sample_ignores_input_order():
    cands = [(i, "a") for i in range(30)] + [(100 + i, "b") for i in range(30)]
    assert sample_verify(cands, 5) == sample_verify(list(reversed(cands)), 5)


def test_labels_are_the_d1_classes_plus_cant_tell():
    assert valid_label("mixed-use") and valid_label(CANT_TELL)
    assert not valid_label("restaurant") and not valid_label("") and not valid_label("Residential")
    assert len(LABELS) == 8


def test_kappa_is_one_for_agreement_zero_for_chance_and_corrects_for_a_majority_class():
    a = ["r", "r", "c", "c"]
    assert cohens_kappa(a, a) == 1.0
    assert cohens_kappa(["r", "r", "c", "c"], ["r", "c", "r", "c"]) == pytest.approx(0.0)
    # 90% raw agreement, but only because nearly everything is "r": kappa is far lower
    truth = ["r"] * 18 + ["c", "c"]
    guess = ["r"] * 20
    assert cohens_kappa(truth, guess) == pytest.approx(0.0)


class _NoCommit:
    """Wraps a connection so the API's commit never persists: each test rolls back."""

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
            conn.execute("SELECT 1 FROM human_label LIMIT 1")
            return bool(conn.execute("SELECT count(*) FROM image_pick").fetchone()[0])
    except (psycopg.Error, KeyError):
        return False


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STREETWALKER_REVIEW", "1")
    import importlib

    from streetwalker import api, deps

    importlib.reload(api)  # the router is mounted at import time, only when the flag is set
    conn = db.connect()
    conn.row_factory = dict_row
    api.app.dependency_overrides[deps.get_conn] = lambda: _NoCommit(conn)
    # a private queue inside the transaction: three buildings that have a photo, so nothing real is touched
    ids = [r["building_id"] for r in conn.execute("SELECT building_id FROM image_pick ORDER BY building_id LIMIT 3").fetchall()]
    conn.execute("DELETE FROM review_item WHERE set_name = 'verify'")
    conn.execute("DELETE FROM human_label WHERE set_name = 'verify'")
    for rank, bid in enumerate(ids, 1):
        conn.execute("INSERT INTO review_item (set_name, building_id, rank) VALUES ('verify', %s, %s)", (bid, rank))
    yield TestClient(api.app), ids
    conn.rollback()
    conn.close()
    monkeypatch.delenv("STREETWALKER_REVIEW")
    importlib.reload(api)


needs_db = pytest.mark.skipif(not _ready(), reason="needs the local DB with image picks and migration 016")


@needs_db
def test_labelling_flow_next_label_undo(client):
    http, ids = client
    first = http.get("/review/next", params={"set_name": "verify"}).json()
    assert first["total"] == 3 and first["labelled"] == 0 and first["item"]["building_id"] == ids[0]
    item = first["item"]
    assert item["target"]["type"] == "Polygon" and item["address"].startswith("Building at")
    # labelling is blind: nothing in the payload names ground truth or a prediction
    assert not any(k in item for k in ("truth", "d1_class", "prediction", "probs", "confidence", "land_use"))

    ok = http.post("/review/label", json={"building_id": ids[0], "set_name": "verify", "label": "mixed-use", "seconds": 4.2, "evidence_shown": True})
    assert ok.status_code == 200
    second = http.get("/review/next", params={"set_name": "verify"}).json()
    assert second["labelled"] == 1 and second["item"]["building_id"] == ids[1]

    assert http.post("/review/undo", params={"set_name": "verify"}).json() == {"undone": ids[0]}
    again = http.get("/review/next", params={"set_name": "verify"}).json()
    assert again["labelled"] == 0 and again["item"]["building_id"] == ids[0]


@needs_db
def test_the_last_label_wins_and_cant_tell_is_accepted(client):
    http, ids = client
    for label in ("residential", CANT_TELL):
        assert http.post("/review/label", json={"building_id": ids[0], "set_name": "verify", "label": label}).status_code == 200
    from streetwalker.review import latest_labels

    conn = http.app.dependency_overrides[next(iter(http.app.dependency_overrides))]()._conn
    assert latest_labels(conn, "verify")[ids[0]][0] == CANT_TELL


@needs_db
def test_bad_labels_and_foreign_buildings_are_rejected(client):
    http, ids = client
    bad = http.post("/review/label", json={"building_id": ids[0], "set_name": "verify", "label": "restaurant"})
    assert bad.status_code == 422
    assert http.post("/review/label", json={"building_id": -5, "set_name": "verify", "label": "residential"}).status_code == 404
    assert http.post("/review/label", json={"building_id": ids[0], "set_name": "verify", "label": "vacant", "seconds": -1}).status_code == 422
    assert http.get("/review/next", params={"set_name": "nope"}).status_code == 422


@needs_db
def test_images_are_served_only_for_queued_buildings(client):
    http, ids = client
    assert http.get("/review/image/-5/photo").status_code == 404
    assert http.get(f"/review/image/{ids[0]}/../../etc/passwd").status_code in (404, 422)
    r = http.get(f"/review/image/{ids[0]}/photo")
    assert r.status_code in (200, 404)  # 404 only when the photo was never downloaded
    if r.status_code == 200:
        assert r.headers["content-type"] == "image/jpeg"


def test_review_endpoints_are_off_unless_enabled(monkeypatch):
    monkeypatch.delenv("STREETWALKER_REVIEW", raising=False)
    import importlib

    from streetwalker import api

    importlib.reload(api)
    assert not any(r.path.startswith("/review") for r in api.app.routes)


@needs_db
def test_report_scores_labels_against_ground_truth(capsys):
    from streetwalker.review import report

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT g.building_id, g.d1_class FROM ground_truth g JOIN image_pick ip ON ip.building_id = g.building_id ORDER BY g.building_id LIMIT 5"
        ).fetchall()
        conn.execute("DELETE FROM human_label")
        agree, differ, cant = rows[:3], rows[3], rows[4]
        for bid, d1 in agree:  # three labels equal to the parcel truth
            conn.execute("INSERT INTO human_label (building_id, set_name, label, seconds) VALUES (%s, 'verify', %s, 5)", (bid, d1))
        wrong = "vacant" if differ[1] != "vacant" else "other"
        conn.execute("INSERT INTO human_label (building_id, set_name, label, seconds) VALUES (%s, 'verify', %s, 15)", (differ[0], wrong))
        conn.execute("INSERT INTO human_label (building_id, set_name, label, seconds) VALUES (%s, 'verify', 'cant_tell', 30)", (cant[0],))
        report(conn)
        conn.rollback()
    out = capsys.readouterr().out
    assert "5 labelled buildings; 1 marked can't tell (20%); 4 scored" in out
    assert "agreement 0.750" in out  # 3 of the 4 scored labels match the truth
    assert "median 5.0, mean 12.0" in out  # seconds 5, 5, 5, 15, 30
