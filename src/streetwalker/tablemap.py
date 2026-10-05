"""TableMap retrieval: place search joined to the provisional aspect ratings and to review text (decision 0023).

PRIVATE: reads Yelp-derived tables (yelp_review through the place_review view, restaurant_aspect, restaurant_rating,
aspect_score). Only the TableMap router (STREETWALKER_TABLEMAP=1) uses it; the default API never imports it.

PROVISIONAL: every rating and aspect number here comes from the provisional rating (decision 0021), whose aspect scores
are not validated against people. Results carry that status; a sort by a rating is opt-in (`rank_by`) and the rank
interval is returned beside it.

What "hybrid" means: structured place filters (kind, area, transit, distance), constraints on the aspect posteriors, and review
retrieval are combined in one query. Retrieval has two rankers over the reviews of the places that pass the filters: lexical
(Postgres full-text search) and dense (exact cosine distance to the question's embedding, decision 0024). `mode` picks one or
both; hybrid fuses the two ranks by reciprocal-rank fusion (a review scores the sum of 1 / (60 + rank) over the lists that
hold it), and a place's text score is the sum over its reviews.

Like search.py, every user value is a bound parameter. The only text spliced into the SQL is built from fixed names.
"""

import re
from dataclasses import dataclass, field, replace

from streetwalker.aspects import ASPECTS
from streetwalker.search import SELECT, SORTS, BadQuery, PlaceQuery, parts

TEXT_CONFIG = "english"
RANK_BY = ("text", "composite", *ASPECTS)
MIN_BY = ("mean", "lower")  # compare the aspect posterior mean, or its 95% lower bound ("confidently at least this good")
MODES = ("lexical", "dense", "hybrid")
RRF_K = 60  # the usual constant of reciprocal-rank fusion: it damps the weight of the very top ranks
DENSE_K = 100  # reviews the dense ranker contributes
MAX_EXCERPTS = 5
MAX_TEXT = 200
HEADLINE = 'MaxWords=45, MinWords=20, ShortWord=2, MaxFragments=2, FragmentDelimiter=" ... ", StartSel="«", StopSel="»"'  # no HTML in snippets
ASPECT_FIELDS = (("mean", "mean"), ("lo", "ci_low"), ("hi", "ci_high"), ("n_mentions", "n_mentions"), ("n_eff", "n_eff"))


@dataclass
class TableQuery:
    place: PlaceQuery = field(default_factory=PlaceQuery)
    text: str | None = None  # only places with a review matching this (web-search syntax: words, "phrases", -exclude, or)
    min_aspect: dict[str, float] = field(default_factory=dict)  # aspect -> threshold on the 0 to 1 scale
    min_by: str = "mean"
    min_reviews: int | None = None
    reviewed_only: bool = False  # drop places with no linked Yelp reviews
    rank_by: str | None = None  # opt-in sort by a provisional score; otherwise the place sort applies
    excerpts: int = 0  # matching review passages to return per place, when text is given
    mode: str = "lexical"  # lexical | dense | hybrid (the router defaults to hybrid)
    query_vec: list[float] | None = None  # the embedded question, for dense and hybrid
    embed_model: str | None = None  # model id the vectors must come from (embeddings.model_id())
    min_similarity: float | None = None  # cosine floor on dense candidates; None keeps the top DENSE_K whatever their similarity
    dense_k: int = DENSE_K


def _check(tq: TableQuery) -> None:
    if tq.text is not None and not tq.text.strip():
        raise BadQuery("text must not be empty")
    if tq.text and len(tq.text) > MAX_TEXT:
        raise BadQuery(f"text is at most {MAX_TEXT} characters")
    for a, v in tq.min_aspect.items():
        if a not in ASPECTS:
            raise BadQuery(f"unknown aspect {a!r}; use one of {', '.join(ASPECTS)}")
        if not 0.0 <= v <= 1.0:
            raise BadQuery("aspect thresholds are on the 0 to 1 scale")
    if tq.min_by not in MIN_BY:
        raise BadQuery(f"min_by must be one of {', '.join(MIN_BY)}")
    if tq.rank_by is not None and tq.rank_by not in RANK_BY:
        raise BadQuery(f"rank_by must be one of {', '.join(RANK_BY)}")
    if tq.rank_by == "text" and not tq.text:
        raise BadQuery("rank_by=text needs text")
    if not 0 <= tq.excerpts <= MAX_EXCERPTS:
        raise BadQuery(f"excerpts must be 0 to {MAX_EXCERPTS}")
    if tq.excerpts and not tq.text:
        raise BadQuery("excerpts needs text")
    if tq.mode not in MODES:
        raise BadQuery(f"mode must be one of {', '.join(MODES)}")
    if tq.text and tq.mode != "lexical" and (tq.query_vec is None or tq.embed_model is None):
        raise BadQuery(f"mode={tq.mode} needs the embedded question")
    if tq.min_similarity is not None and not -1.0 <= tq.min_similarity <= 1.0:
        raise BadQuery("min_similarity is a cosine, between -1 and 1")
    if not 1 <= tq.dense_k <= 500:
        raise BadQuery("dense_k is 1 to 500")


# The latest provisional rating run and its aspect posteriors, pivoted to one row per place.
CTES = """
    latest AS (SELECT id, aspect_run_id, weights_version FROM rating_run ORDER BY id DESC LIMIT 1),
    asp AS (
        SELECT place_id,
{pivot}
        FROM restaurant_aspect WHERE run_id = (SELECT id FROM latest) GROUP BY place_id
    )"""

def exclusions(text: str) -> str | None:
    """The -excluded words of a web-search style query, as an OR query, or None. Dense candidates are not found by words, so
    this is how an exclusion still holds for them."""
    words = re.findall(r"(?:^|\s)-([^\s\-][^\s]*)", text)
    return " or ".join(words) if words else None


def retrieval_ctes(mode: str, scope_sql: str) -> str:
    """CTEs ending in `fused` (place_id, review_id, score) and `place_text` (n_hits, text_score) over the reviews of the places
    in `scope_sql`. `tq` is always defined, because passages are highlighted with the lexical query."""
    cfg = TEXT_CONFIG
    ctes = [f"scope AS ({scope_sql})", f"tq AS (SELECT websearch_to_tsquery('{cfg}', %(text)s) AS q)"]
    ranked = []
    if mode in ("lexical", "hybrid"):
        ctes += [
            f"""fts AS (
        SELECT DISTINCT ON (r.review_id) pr.place_id, r.review_id, ts_rank_cd(to_tsvector('{cfg}', r.text), tq.q) AS rank
        FROM place_review pr JOIN yelp_review r USING (review_id), tq
        WHERE pr.place_id IN (SELECT place_id FROM scope) AND to_tsvector('{cfg}', r.text) @@ tq.q
        ORDER BY r.review_id, pr.place_id
    )""",
            "fts_ranked AS (SELECT place_id, review_id, row_number() OVER (ORDER BY rank DESC, review_id) AS r FROM fts)",
        ]
        ranked.append("fts_ranked")
    if mode in ("dense", "hybrid"):
        ctes += [
            f"""dense AS (
        SELECT DISTINCT ON (e.review_id) pr.place_id, e.review_id, 1 - (e.embedding <=> %(qvec)s::vector) AS sim
        FROM place_review pr JOIN review_embedding e ON e.review_id = pr.review_id AND e.model = %(emodel)s
        JOIN yelp_review r ON r.review_id = e.review_id
        WHERE pr.place_id IN (SELECT place_id FROM scope)
          AND (%(min_sim)s::float IS NULL OR 1 - (e.embedding <=> %(qvec)s::vector) >= %(min_sim)s)
          AND (%(excl)s::text IS NULL OR NOT to_tsvector('{cfg}', r.text) @@ websearch_to_tsquery('{cfg}', %(excl)s))
        ORDER BY e.review_id, pr.place_id
    )""",
            (
                "dense_ranked AS (SELECT place_id, review_id, row_number() OVER (ORDER BY sim DESC, review_id) AS r "
                "FROM (SELECT * FROM dense ORDER BY sim DESC, review_id LIMIT %(dense_k)s) d)"
            ),
        ]
        ranked.append("dense_ranked")
    union = " UNION ALL ".join(f"SELECT place_id, review_id, r FROM {n}" for n in ranked)
    ctes += [
        f"fused AS (SELECT place_id, review_id, sum(1.0 / ({RRF_K} + r))::float AS score FROM ({union}) u GROUP BY place_id, review_id)",
        "place_text AS (SELECT place_id, count(*) AS n_hits, sum(score) AS text_score FROM fused GROUP BY place_id)",
    ]
    return ",\n    ".join(ctes)


def retrieval_params(tq: TableQuery) -> dict:
    out = {"text": tq.text.strip(), "min_sim": tq.min_similarity, "dense_k": tq.dense_k, "excl": exclusions(tq.text)}
    if tq.mode != "lexical":
        from streetwalker.embeddings import (
            vec_literal,  # imported here: the lexical path needs no embedding module
        )

        out.update(qvec=vec_literal(tq.query_vec), emodel=tq.embed_model)
    return out


EXTRA_COLS = (
    ["l.id AS rating_run", "l.aspect_run_id", "l.weights_version",
     "rr.composite", "rr.ci_low AS composite_lo", "rr.ci_high AS composite_hi", "rr.rank AS composite_rank",
     "rr.rank_low AS composite_rank_lo", "rr.rank_high AS composite_rank_hi", "rr.stars_shrunk", "rr.n_reviews",
     "(rr.place_id IS NOT NULL) AS has_reviews"]
    + [f"asp.{a}_{k} AS {a}_{k}" for a in ASPECTS for k, _ in ASPECT_FIELDS]
)

RANK_SQL = {"composite": "rr.composite DESC NULLS LAST, p.id", "text": "text_score DESC NULLS LAST, p.id"} | {
    a: f"asp.{a}_mean DESC NULLS LAST, p.id" for a in ASPECTS
}


def build(tq: TableQuery) -> tuple[str, dict]:
    """Return (sql, params). Raises BadQuery for combinations that cannot be answered."""
    _check(tq)
    place = replace(tq.place, sort=None) if tq.rank_by else tq.place  # rank_by replaces the place sort
    pt = parts(place)
    where, params = list(pt.where), dict(pt.params)

    bound = "mean" if tq.min_by == "mean" else "lo"
    for a, v in tq.min_aspect.items():  # `a` is checked against ASPECTS, so the f-string only ever holds a fixed name
        where.append(f"asp.{a}_{bound} >= %(min_{a})s")
        params[f"min_{a}"] = v
    if tq.min_reviews is not None:
        where.append("rr.n_reviews >= %(min_reviews)s")
        params["min_reviews"] = tq.min_reviews
    if tq.reviewed_only:
        where.append("rr.place_id IS NOT NULL")
    where_sql = "    WHERE " + "\n      AND ".join(where) + "\n" if where else ""

    pivot = ",\n".join(f"            max({col}) FILTER (WHERE aspect = '{a}') AS {a}_{k}" for a in ASPECTS for k, col in ASPECT_FIELDS)
    ctes = CTES.format(pivot=pivot)
    extra = ", " + ", ".join(EXTRA_COLS)
    joins = " LEFT JOIN latest l ON true LEFT JOIN restaurant_rating rr ON rr.run_id = l.id AND rr.place_id = p.id LEFT JOIN asp ON asp.place_id = p.id"
    if tq.text:
        # Review retrieval runs over the reviews of the places that pass every other filter (so "bar" + "patio" cannot lose
        # its answer to a better-matching restaurant), then the places are joined back.
        base = f"SELECT p.id AS place_id FROM place p JOIN area a ON a.id = p.area_id{joins}\n{where_sql}"
        ctes += ",\n    base AS (" + base + "    ),\n    " + retrieval_ctes(tq.mode, "SELECT place_id FROM base")
        joins += " JOIN place_text pt ON pt.place_id = p.id"
        extra += ", pt.n_hits, pt.text_score"
        params.update(retrieval_params(tq))
    else:
        extra += ", NULL::bigint AS n_hits, NULL::float AS text_score"

    if tq.rank_by:
        order = RANK_SQL[tq.rank_by]
    elif tq.text and tq.place.sort is None:
        order = RANK_SQL["text"]
    else:
        order = SORTS[pt.sort]
    sql = "WITH" + ctes + SELECT.format(distance=pt.distance, score=pt.score, extra=extra, joins=joins) + where_sql
    sql += f"    ORDER BY {order}\n    LIMIT %(limit)s OFFSET %(offset)s"
    return sql, params


def excerpts_sql(mode: str) -> str:
    """Top review passages per place, ranked like the search ranks reviews. The headline is computed only for the rows that survive the cut."""
    return f"""
    WITH {retrieval_ctes(mode, "SELECT unnest(%(place_ids)s::int[]) AS place_id")},
    top AS (
        SELECT *, row_number() OVER (PARTITION BY place_id ORDER BY score DESC, review_id) AS rn FROM fused
    )
    SELECT t.place_id, t.review_id, t.score, r.date, r.stars, r.useful,
           ts_headline('{TEXT_CONFIG}', r.text, tq.q, '{HEADLINE}') AS snippet,
           {"1 - (e.embedding <=> %(qvec)s::vector)" if mode != "lexical" else "NULL::float"} AS similarity
    FROM top t JOIN yelp_review r USING (review_id)
    {"LEFT JOIN review_embedding e ON e.review_id = t.review_id AND e.model = %(emodel)s" if mode != "lexical" else ""}, tq
    WHERE t.rn <= %(k)s
    ORDER BY t.place_id, t.rn"""


def load_excerpts(conn, place_ids: list[int], tq: TableQuery, aspect_run_id: int | None) -> dict[int, list[dict]]:
    """Matching review passages per place (tq.text, tq.mode, tq.excerpts), each with the aspect scores Jev gave that review
    (a level only where it was mentioned). Passages are ranked by the same fusion as the search, over these places only."""
    k = tq.excerpts
    if not place_ids or not tq.text or k <= 0:
        return {}
    _check(tq)
    rows = conn.execute(excerpts_sql(tq.mode), {**retrieval_params(tq), "place_ids": place_ids, "k": k}).fetchall()
    scores: dict[str, dict[str, dict]] = {}
    if aspect_run_id is not None and rows:
        for s in conn.execute(
            "SELECT review_id, aspect, mentioned, score FROM aspect_score WHERE run_id = %s AND review_id = ANY(%s)",
            (aspect_run_id, [r["review_id"] for r in rows]),
        ).fetchall():
            scores.setdefault(s["review_id"], {})[s["aspect"]] = {
                "mentioned": round(s["mentioned"], 3), "level": round(s["score"], 2) if s["mentioned"] >= 0.5 else None,
            }
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["place_id"], []).append({
            "review_id": r["review_id"], "date": r["date"].isoformat(), "stars": r["stars"], "useful": r["useful"],
            "snippet": r["snippet"], "match": round(r["score"], 4), "similarity": None if r["similarity"] is None else round(r["similarity"], 3),
            "aspects": scores.get(r["review_id"], {}),
        })
    return out


def shape_rating(row: dict) -> dict | None:
    """The review-derived part of a result row. None for a place with no linked reviews."""
    if not row["has_reviews"]:
        return None
    return {
        "status": "provisional",
        "weights_version": row["weights_version"],
        "n_reviews": row["n_reviews"],
        "composite": {
            "mean": round(row["composite"], 2), "lo": round(row["composite_lo"], 2), "hi": round(row["composite_hi"], 2),
            "rank": row["composite_rank"], "rank_lo": row["composite_rank_lo"], "rank_hi": row["composite_rank_hi"],
        },
        "stars_shrunk": round(row["stars_shrunk"], 2),
        "aspects": {
            a: {k: None if row[f"{a}_{k}"] is None else round(row[f"{a}_{k}"], 3 if k in ("mean", "lo", "hi") else 1) for k, _ in ASPECT_FIELDS}
            for a in ASPECTS
        },
    }
