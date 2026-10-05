"""TableMap retrieval tests (decision 0023). Every review, place and score here is invented: Yelp data never enters the repository.

The database tests build a private world inside one transaction (five invented places in a spot outside the survey areas, so
the real rows cannot match) and roll it back. They need the local database with migration 022 but not any real data.
"""

import inspect
import os
import subprocess
import sys

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from streetwalker import db, tablemap, tablemap_api
from streetwalker.search import BadQuery, PlaceQuery
from streetwalker.tablemap import TableQuery, build

HERE = (39.9700, -75.1000)  # invented places sit here: inside the API's lat/lng bounds, outside the three survey areas
NEAR = {"lat": HERE[0], "lng": HERE[1], "radius_m": 500}


# ---- the query builder, no database ------------------------------------------------------------------------------------

def test_user_text_only_ever_travels_as_a_bound_parameter():
    evil = "x'); DROP TABLE yelp_review; --"
    sql, params = build(TableQuery(PlaceQuery(q=evil), text=evil, min_aspect={"food": 0.5}))
    assert "DROP TABLE" not in sql and evil not in sql
    assert evil in params.values()


def test_impossible_requests_are_rejected_before_any_query():
    bad = [
        TableQuery(rank_by="text"),  # nothing to rank by
        TableQuery(excerpts=2),  # excerpts come from matching text
        TableQuery(text="   "),
        TableQuery(text="a" * 500),
        TableQuery(min_aspect={"parking": 0.5}),
        TableQuery(min_aspect={"food": 1.5}),
        TableQuery(min_by="median"),
        TableQuery(rank_by="stars"),
        TableQuery(text="x", excerpts=99),
        TableQuery(place=PlaceQuery(sort="distance")),  # the place rules still apply
    ]
    for tq in bad:
        with pytest.raises(BadQuery):
            build(tq)


def test_ordering_rules():
    assert "text_score DESC" in build(TableQuery(text="patio"))[0].rsplit("ORDER BY", 1)[1]  # text given, no sort chosen
    assert "rr.composite DESC" in build(TableQuery(rank_by="composite"))[0].rsplit("ORDER BY", 1)[1]
    # an explicit place sort is kept, a rank_by replaces it
    assert "distance_m" in build(TableQuery(PlaceQuery(lat=39.9, lng=-75.1, sort="distance"), text="patio"))[0].rsplit("ORDER BY", 1)[1]
    assert "asp.food_mean DESC" in build(TableQuery(PlaceQuery(sort="name"), rank_by="food"))[0].rsplit("ORDER BY", 1)[1]


def test_retrieval_reads_reviews_only_through_the_usable_link_and_never_the_labels():
    src = inspect.getsource(tablemap) + inspect.getsource(tablemap_api)
    assert "place_review" in src
    assert "aspect_label" not in src and "human_label" not in src
    import re

    assert not re.search(r"\byelp_link\b", src)  # low-confidence links attach the wrong reviews; use place_review / yelp_link_usable


def _routes(env_flag: str | None) -> set[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("STREETWALKER_TABLEMAP", "STREETWALKER_REVIEW")}
    if env_flag:
        env["STREETWALKER_TABLEMAP"] = env_flag
    out = subprocess.run(
        [sys.executable, "-c", "from streetwalker.api import app; print('\\n'.join(app.openapi()['paths']))"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert out.returncode == 0, out.stderr[-800:]
    return set(out.stdout.split())


def test_the_default_app_is_yelp_free_and_the_flag_mounts_tablemap():
    default = _routes(None)
    assert default and not any("tablemap" in p or "yelp" in p or "review" in p for p in default)
    assert _routes("0") == default
    assert {"/tablemap/search", "/tablemap/places/{place_id}"} <= _routes("1")


# ---- a private world of invented places ----------------------------------------------------------------------------------

# place -> (kind, linked to Yelp?, reviews [(stars, text, {aspect: (mentioned, level 0-4)})], aspect posterior means)
WORLD = {
    "Quokka Table": ("cafe", True, [
        (5, "Great cold brew and a lovely patio. The staff were friendly.", {"food": (0.95, 4.0), "service": (0.9, 3.0), "atmosphere": (0.9, 4.0)}),
        (5, "The patio is the best in the neighborhood, perfect for a sunny morning.", {"atmosphere": (0.95, 4.0)}),
        (3, "Waited forever for the check, but the pastries are excellent.", {"service": (0.95, 1.0), "food": (0.9, 3.5)}),
    ], {"food": 0.80, "service": 0.50, "atmosphere": 0.85, "value": 0.60}),
    "Marmot Kitchen": ("restaurant", True, [
        (4, "Cozy dining room, the lamb was tender and the service was attentive.", {"atmosphere": (0.9, 3.5), "food": (0.95, 4.0), "service": (0.9, 4.0)}),
        (2, "Overpriced for tiny portions, honestly not worth it.", {"value": (0.97, 0.0)}),
    ], {"food": 0.75, "service": 0.80, "atmosphere": 0.70, "value": 0.20}),
    "Heron Bar": ("bar", True, [
        (4, "Rooftop terrace with a great view and strong cocktails.", {"atmosphere": (0.9, 4.0), "food": (0.7, 3.0)}),
        (3, "Loud music, but the bartender remembered our order.", {"atmosphere": (0.9, 1.0), "service": (0.9, 3.5)}),
    ], {"food": 0.55, "service": 0.70, "atmosphere": 0.80, "value": 0.50}),
    "Newt Noodles": ("restaurant", True, [
        (5, "The ramen broth is rich and the noodles are fresh; cheap and filling.", {"food": (0.97, 4.0), "value": (0.9, 4.0)}),
        (4, "Gluten free options available and the staff handled allergies carefully.", {"service": (0.9, 4.0)}),
    ], {"food": 0.80, "service": 0.77, "atmosphere": 0.50, "value": 0.90}),
    "Ibex Bakery": ("bakery or deli", True, [
        (5, "Sourdough sells out by noon, come early.", {"food": (0.8, 3.5)}),
        (4, "No seating, takeaway only, but the croissants are flaky and buttery.", {"food": (0.95, 4.0), "atmosphere": (0.6, 1.5)}),
    ], {"food": 0.90, "service": 0.60, "atmosphere": 0.40, "value": 0.70}),
    "Walrus Diner": ("restaurant", False, [], {}),  # a census place with no Yelp link: appears in plain search, never in review search
}
COMPOSITE = {"Ibex Bakery": 4.2, "Newt Noodles": 4.1, "Quokka Table": 3.9, "Marmot Kitchen": 3.8, "Heron Bar": 3.6}


def _ready() -> bool:
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1 FROM yelp_review LIMIT 1")
            conn.execute("SELECT 1 FROM rating_run LIMIT 1")
            return bool(conn.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'yelp_review_fts_idx'").fetchone())
    except (psycopg.Error, KeyError):
        return False


needs_db = pytest.mark.skipif(not _ready(), reason="needs the local DB with migrations 017 to 022")


def seed(conn) -> dict[str, int]:
    """Insert the invented world and return place ids by name. The caller rolls back."""
    area = conn.execute(
        "INSERT INTO area (slug, name, profile, geom) VALUES ('zz-test', 'ZZ test area', 'invented', "
        "ST_GeomFromText('POLYGON((-75.11 39.96, -75.09 39.96, -75.09 39.98, -75.11 39.98, -75.11 39.96))', 4326)) RETURNING id"
    ).fetchone()["id"]
    ar = conn.execute("INSERT INTO aspect_run (purpose, prompt_version, model_version) VALUES ('test', 'a1', 'test') RETURNING id").fetchone()["id"]
    rr = conn.execute("INSERT INTO rating_run (aspect_run_id, weights_version, params) VALUES (%s, 'w1', '{}'::jsonb) RETURNING id", (ar,)).fetchone()["id"]
    ids: dict[str, int] = {}
    for i, (name, (kind, linked, reviews, means)) in enumerate(WORLD.items()):
        pid = conn.execute(
            "INSERT INTO place (area_id, name, kind, geom, sources, confidence, address) VALUES (%s, %s, %s, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326), ARRAY['osm'], 'high', %s) RETURNING id",
            (area, name, kind, HERE[1] + 0.0005 * i, HERE[0], f"{i} Invented St"),
        ).fetchone()["id"]
        ids[name] = pid
        if not linked:
            continue
        biz = f"zz-biz-{i}"
        conn.execute("INSERT INTO yelp_business (business_id, name, geom, is_food) VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), true)",
                     (biz, name, HERE[1] + 0.0005 * i, HERE[0]))
        conn.execute("INSERT INTO yelp_link (place_id, business_id, score, basis, name_sim, dist_m, confidence) VALUES (%s, %s, 1, 'test', 1, 0, 'high')", (pid, biz))
        for j, (stars, text, aspects) in enumerate(reviews):
            rid = f"zz-rev-{i}-{j}"
            conn.execute("INSERT INTO yelp_review (review_id, business_id, stars, date, text) VALUES (%s, %s, %s, '2021-06-01', %s)", (rid, biz, stars, text))
            for a in tablemap.ASPECTS:
                m, level = aspects.get(a, (0.05, 2.0))
                conn.execute("INSERT INTO aspect_score (run_id, review_id, aspect, mentioned, score, confidence, probs) VALUES (%s, %s, %s, %s, %s, 0.9, '[0.2,0.2,0.2,0.2,0.2]'::jsonb)",
                             (ar, rid, a, m, level))
        for a, mean in means.items():
            conn.execute("INSERT INTO restaurant_aspect (run_id, place_id, aspect, mean, ci_low, ci_high, n_mentions, n_eff) VALUES (%s, %s, %s, %s, %s, %s, 5, 4)",
                         (rr, pid, a, mean, mean - 0.1, mean + 0.1))
        comp = COMPOSITE[name]
        conn.execute(
            "INSERT INTO restaurant_rating (run_id, place_id, composite, ci_low, ci_high, rank, rank_low, rank_high, stars_shrunk, n_reviews) "
            "VALUES (%s, %s, %s, %s, %s, %s, 1, 5, 3.5, %s)",
            (rr, pid, comp, comp - 0.4, comp + 0.4, sorted(COMPOSITE.values(), reverse=True).index(comp) + 1, len(reviews)),
        )
    return ids


@pytest.fixture
def world():
    conn = db.connect()
    conn.row_factory = dict_row
    ids = seed(conn)
    yield conn, ids
    conn.rollback()
    conn.close()


def names(conn, tq: TableQuery) -> list[str]:
    tq.place = PlaceQuery(**{**tq.place.__dict__, "lat": HERE[0], "lng": HERE[1], "radius_m": 500, "limit": 50})
    sql, params = build(tq)
    return [r["name"] for r in conn.execute(sql, params).fetchall()]


@needs_db
def test_plain_search_lists_the_unreviewed_place_with_no_rating_and_reviewed_only_drops_it(world):
    conn, _ = world
    assert sorted(names(conn, TableQuery())) == sorted(WORLD)
    assert "Walrus Diner" not in names(conn, TableQuery(reviewed_only=True))
    assert "Walrus Diner" not in names(conn, TableQuery(min_reviews=1))


# Retrieval evaluation: query -> the places a person would call relevant (from the invented reviews above).
LEXICAL = [
    ("patio", {"Quokka Table"}),
    ("terrace", {"Heron Bar"}),
    ("ramen noodles", {"Newt Noodles"}),
    ('"cold brew"', {"Quokka Table"}),
    ("waiting", {"Quokka Table"}),  # stemming: the review says "Waited"
    ("cozy -patio", {"Marmot Kitchen"}),
    ("croissants OR sourdough", {"Ibex Bakery"}),
    ("gluten free", {"Newt Noodles"}),
    ("patio OR terrace", {"Quokka Table", "Heron Bar"}),
]
# Synonyms the reviews express in other words. Lexical search cannot bridge them; when dense retrieval lands, move these up.
LEXICAL_MISSES = [
    ("al fresco", {"Quokka Table", "Heron Bar"}),
    ("inexpensive", {"Newt Noodles"}),
]


@needs_db
def test_lexical_retrieval_eval(world):
    conn, _ = world
    recall, precision = [], []
    for q, relevant in LEXICAL:
        got = set(names(conn, TableQuery(text=q)))
        recall.append(len(got & relevant) / len(relevant))
        precision.append(len(got & relevant) / len(got) if got else 0.0)
        assert got == relevant, (q, got)
    assert min(recall) == 1.0 and min(precision) == 1.0


@needs_db
def test_known_lexical_misses_are_recorded_not_hidden(world):
    conn, _ = world
    for q, relevant in LEXICAL_MISSES:
        assert set(names(conn, TableQuery(text=q))) & relevant == set(), f"{q!r} now finds results: update the eval and the decision record"


@needs_db
def test_text_search_never_returns_an_unlinked_place(world):
    conn, _ = world
    for q in ("patio", "diner", "walrus", "food"):
        assert "Walrus Diner" not in names(conn, TableQuery(text=q))


@needs_db
def test_filters_combine_with_text_and_aspects(world):
    conn, _ = world
    assert names(conn, TableQuery(PlaceQuery(kinds=["bar"]), text="patio OR terrace")) == ["Heron Bar"]
    assert names(conn, TableQuery(text="patio OR terrace", min_aspect={"food": 0.7})) == ["Quokka Table"]
    assert sorted(names(conn, TableQuery(min_aspect={"service": 0.76}))) == ["Marmot Kitchen", "Newt Noodles"]
    # the lower bound is stricter than the mean: Newt's service interval starts at 0.67
    assert names(conn, TableQuery(min_aspect={"service": 0.69}, min_by="lower")) == ["Marmot Kitchen"]
    assert names(conn, TableQuery(PlaceQuery(kinds=["bar"]), min_aspect={"food": 0.9})) == []


@needs_db
def test_rank_by_is_opt_in_descending_and_unrated_places_go_last(world):
    conn, _ = world
    assert names(conn, TableQuery(rank_by="composite"))[:5] == sorted(COMPOSITE, key=COMPOSITE.get, reverse=True)
    assert names(conn, TableQuery(rank_by="composite"))[-1] == "Walrus Diner"
    assert names(conn, TableQuery(rank_by="value"))[0] == "Newt Noodles"
    assert names(conn, TableQuery(rank_by="food"))[0] == "Ibex Bakery"
    assert names(conn, TableQuery()) == sorted(WORLD, key=str.lower)  # the default stays alphabetical, not a ranking


# ---- over HTTP --------------------------------------------------------------------------------------------------------

@pytest.fixture
def http(world):
    from streetwalker import deps

    conn, ids = world
    app = FastAPI()
    app.include_router(tablemap_api.router)
    app.dependency_overrides[deps.get_conn] = lambda: conn
    return TestClient(app), ids


@needs_db
def test_every_response_and_every_rated_place_says_provisional(http):
    client, ids = http
    r = client.get("/tablemap/search", params={**NEAR, "excerpts": 0}).json()
    assert r["status"] == "provisional" and "PROVISIONAL" in r["banner"] and r["basis"]["weights_version"] == "w1"
    assert r["basis"]["reviews_through"] and "Yelp Open Dataset" in " ".join(r["attribution"])
    rated = [i for i in r["items"] if i["reviews"]]
    assert len(rated) == 5 and all(i["reviews"]["status"] == "provisional" for i in rated)
    walrus = next(i for i in r["items"] if i["name"] == "Walrus Diner")
    assert walrus["reviews"] is None and walrus["text_match"] is None
    d = client.get(f"/tablemap/places/{ids['Quokka Table']}").json()
    assert d["status"] == "provisional" and d["reviews"]["status"] == "provisional"
    # the rank interval travels with the rank
    c = d["reviews"]["composite"]
    assert c["rank_lo"] <= c["rank"] <= c["rank_hi"] and c["lo"] <= c["mean"] <= c["hi"]
    # the aspect posteriors carry their intervals and sample sizes
    assert set(d["reviews"]["aspects"]) == set(tablemap.ASPECTS)
    assert set(d["reviews"]["aspects"]["food"]) == {"mean", "lo", "hi", "n_mentions", "n_eff"}


@needs_db
def test_excerpts_carry_the_matching_passage_and_per_review_aspect_scores(http):
    client, _ = http
    r = client.get("/tablemap/search", params={**NEAR, "text": "patio", "excerpts": 2}).json()
    assert [i["name"] for i in r["items"]] == ["Quokka Table"]
    ex = r["items"][0]["excerpts"]
    assert len(ex) == 2 and r["items"][0]["text_match"]["n_reviews"] == 2
    assert all("«patio»" in e["snippet"].lower() and "<" not in e["snippet"] for e in ex)
    top = next(e for e in ex if e["review_id"] == "zz-rev-0-0")
    assert top["aspects"]["service"]["level"] == 3.0  # mentioned, so a level is given
    assert top["aspects"]["value"] == {"mentioned": 0.05, "level": None}  # not mentioned, so no level to misread
    assert all(e["date"] == "2021-06-01" and e["review_id"].startswith("zz-rev-") for e in ex)


@needs_db
def test_detail_endpoint_with_text_and_404(http):
    client, ids = http
    d = client.get(f"/tablemap/places/{ids['Marmot Kitchen']}", params={"text": "overpriced", "excerpts": 3}).json()
    assert [e["review_id"] for e in d["excerpts"]] == ["zz-rev-1-1"] and d["excerpts"][0]["aspects"]["value"]["level"] == 0.0
    assert client.get("/tablemap/places/999999999").status_code == 404
    assert client.get(f"/tablemap/places/{ids['Walrus Diner']}").json()["reviews"] is None


@needs_db
def test_http_rejects_bad_requests_without_a_server_error(http):
    client, _ = http
    for params in ({"rank_by": "text"}, {"excerpts": 2}, {"min_food": 1.5}, {"rank_by": "stars"}, {"excerpts": 9, "text": "x"}, {"text": "a" * 300},
                   {"min_by": "median"}, {"sort": "distance"}):
        assert client.get("/tablemap/search", params=params).status_code == 422, params
    assert client.get("/tablemap/search", params={"text": "x'); DROP TABLE yelp_review; --", **NEAR}).status_code == 200
    assert client.get("/tablemap/search", params={"text": "the and of", **NEAR}).json()["items"] == []  # all stopwords match nothing
