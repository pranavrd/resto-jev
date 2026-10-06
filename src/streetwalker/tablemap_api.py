"""TableMap endpoints: search over places, aspect ratings and review text (decision 0023).

PRIVATE and LOCAL. These endpoints return Yelp-derived content (review passages, aspect scores, a rating), so api.py mounts
them only when STREETWALKER_TABLEMAP=1 and the default app stays Yelp-free. They are read-only and have no login: do not
expose this port.

PROVISIONAL. The ratings are the provisional ones of decision 0021 (aspect scores from an LLM, tested on constructed cases,
not validated against people). Every response says so, and every rated place repeats it.
"""

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from streetwalker import chat as chat_mod
from streetwalker.api_common import ATTRIBUTION, Filters, to_place
from streetwalker.deps import Conn
from streetwalker.embeddings import EmbeddingUnavailable, dense_text, embed, model_id
from streetwalker.rating import BANNER
from streetwalker.search import BadQuery, PlaceQuery
from streetwalker.tablemap import (
    DENSE_K,
    MAX_EXCERPTS,
    MAX_TEXT,
    TableQuery,
    build,
    load_excerpts,
    shape_rating,
)

router = APIRouter(prefix="/tablemap", tags=["tablemap (private, provisional)"])

YELP_NOTICE = (
    "Review text and the scores derived from it come from the Yelp Open Dataset (Philadelphia, snapshot to January 2022). "
    "Private, local use only; not for display or redistribution (decision 0001)."
)


def with_embedding(tq: TableQuery) -> TableQuery:
    """Embed the question for dense and hybrid retrieval. The review text and the question stay on this machine (local Ollama)."""
    if not tq.text or tq.mode == "lexical":
        return tq
    meaning = dense_text(tq.text)
    if not meaning:
        raise HTTPException(422, f"mode={tq.mode} needs some words to embed; this text is only operators")
    try:
        tq.embed_model = model_id()
        tq.query_vec = embed([meaning], "query")[0]
    except EmbeddingUnavailable as e:
        raise HTTPException(503, f"{e}. Use mode=lexical, or start Ollama and pull the model.") from e
    return tq


def envelope(conn, first_row: dict | None, tq: TableQuery | None = None) -> dict:
    """What every response states up front: the status, how the numbers were made, and how old the reviews are."""
    through = conn.execute("SELECT max(date) AS d FROM yelp_review").fetchone()["d"]
    return {
        "status": "provisional",
        "banner": BANNER,
        "basis": {
            "rating_run": first_row and first_row["rating_run"], "aspect_run": first_row and first_row["aspect_run_id"],
            "weights_version": first_row and first_row["weights_version"], "reviews_through": through and through.isoformat(),
            "aspect_scale": "0 to 1 posterior mean; 0.5 is the middle level (mixed or flat), 0.75 is mostly good",
        },
        "retrieval": None if tq is None or not tq.text else {
            "mode": tq.mode, "embedding_model": tq.embed_model, "min_similarity": tq.min_similarity,
            "dense_k": tq.dense_k if tq.mode != "lexical" else None,
            "embedded_reviews": conn.execute("SELECT count(*) AS n FROM review_embedding WHERE model = %s", (tq.embed_model,)).fetchone()["n"] if tq.embed_model else None,
            "score": "reciprocal-rank fusion of the lexical and dense ranks, summed over a place's matching reviews",
        },
    }


def item(row: dict, excerpts: dict[int, list[dict]]) -> dict:
    return {**to_place(row), "reviews": shape_rating(row), "text_match": None if row["n_hits"] is None else {"n_reviews": row["n_hits"], "score": round(row["text_score"], 3)},
            "excerpts": excerpts.get(row["id"], [])}


def run(conn, tq: TableQuery) -> tuple[list[dict], int, dict]:
    tq = with_embedding(tq)
    try:
        sql, params = build(tq)
    except BadQuery as e:
        raise HTTPException(422, str(e)) from e
    rows = conn.execute(sql, params).fetchall()
    first = rows[0] if rows else None
    if first is None:  # an empty page still reports the basis
        first = conn.execute("SELECT id AS rating_run, aspect_run_id, weights_version FROM rating_run ORDER BY id DESC LIMIT 1").fetchone()
    ex = load_excerpts(conn, [r["id"] for r in rows], tq, first and first["aspect_run_id"]) if tq.excerpts else {}
    return [item(r, ex) for r in rows], (rows[0]["total"] if rows else 0), envelope(conn, first, tq)


@router.get("/search")
def search(
    conn: Conn,
    pq: Filters,
    text: Annotated[str | None, Query(max_length=MAX_TEXT, description='Only places with a review matching this: words, "a phrase", -excluded, or')] = None,
    min_food: Annotated[float | None, Query(ge=0, le=1)] = None,
    min_atmosphere: Annotated[float | None, Query(ge=0, le=1)] = None,
    min_service: Annotated[float | None, Query(ge=0, le=1)] = None,
    min_value: Annotated[float | None, Query(ge=0, le=1)] = None,
    min_by: Annotated[Literal["mean", "lower"], Query(description="Compare the posterior mean, or its 95% lower bound (confidently at least this good)")] = "mean",
    min_reviews: Annotated[int | None, Query(ge=1)] = None,
    reviewed_only: Annotated[bool, Query(description="Drop places with no linked reviews")] = False,
    rank_by: Annotated[Literal["text", "composite", "food", "atmosphere", "service", "value"] | None, Query(description="Opt-in sort by a PROVISIONAL score; replaces `sort`")] = None,
    excerpts: Annotated[int, Query(ge=0, le=MAX_EXCERPTS, description="Matching review passages per place (needs text)")] = 0,
    mode: Annotated[Literal["lexical", "dense", "hybrid"], Query(description="How `text` finds reviews: words, meaning, or both fused")] = "hybrid",
    min_similarity: Annotated[float | None, Query(ge=-1, le=1, description="Cosine floor for dense matches; unset keeps the closest reviews whatever their similarity")] = None,
    dense_k: Annotated[int, Query(ge=1, le=500, description="Reviews the dense ranker contributes")] = DENSE_K,
) -> dict:
    """Places, filtered by the census filters of /places plus aspect thresholds and review text. Aspect and text results are provisional."""
    mins = {a: v for a, v in {"food": min_food, "atmosphere": min_atmosphere, "service": min_service, "value": min_value}.items() if v is not None}
    tq = TableQuery(pq, text, mins, min_by, min_reviews, reviewed_only, rank_by, excerpts, mode, None, None, min_similarity, dense_k)
    items, total, env = run(conn, tq)
    return {**env, "total": total, "limit": pq.limit, "offset": pq.offset, "items": items, "attribution": [*ATTRIBUTION, YELP_NOTICE]}


@router.get("/places/{place_id}")
def place_detail(
    place_id: int,
    conn: Conn,
    text: Annotated[str | None, Query(max_length=MAX_TEXT, description="Show review passages matching this")] = None,
    excerpts: Annotated[int, Query(ge=0, le=MAX_EXCERPTS)] = 3,
    mode: Annotated[Literal["lexical", "dense", "hybrid"], Query()] = "hybrid",
    min_similarity: Annotated[float | None, Query(ge=-1, le=1)] = None,
) -> dict:
    """One place with its aspect posteriors and, when text is given, the review passages that match it."""
    items, _, env = run(conn, TableQuery(PlaceQuery(place_id=place_id)))
    if not items:
        raise HTTPException(404, "no such place")
    out = items[0]
    if text is not None and excerpts:
        if not text.strip():
            raise HTTPException(422, "text must not be empty")
        tq = with_embedding(TableQuery(PlaceQuery(place_id=place_id), text=text, excerpts=excerpts, mode=mode, min_similarity=min_similarity))
        try:
            out["excerpts"] = load_excerpts(conn, [place_id], tq, env["basis"]["aspect_run"]).get(place_id, [])
        except BadQuery as e:
            raise HTTPException(422, str(e)) from e
        env["retrieval"] = envelope(conn, None, tq)["retrieval"]
    return {**env, **out, "attribution": [*ATTRIBUTION, YELP_NOTICE]}


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=chat_mod.MAX_QUESTION)
    style: Literal["summary", "quotes"] = Field(
        default="summary", description="summary: a model-written sentence per place plus quotes (writer w3). quotes: verbatim quotes only, no model-written text, about three times faster (w4)")


def get_chat_backend() -> chat_mod.ChatBackend:
    """The local chat model. Tests override this dependency."""
    return chat_mod.OllamaChat()


@router.post("/chat")
def chat(body: Ask, conn: Conn, backend: Annotated[chat_mod.ChatBackend, Depends(get_chat_backend)]) -> dict:
    """Ask a question about the places and their reviews. One question, one answer: there is no conversation memory. The answer says
    what search it ran, shows verbatim quotes, and always carries the provisional caveat. Review text goes only to the local model."""
    try:
        out = chat_mod.answer(conn, backend, body.question, run, "w4" if body.style == "quotes" else None)
    except chat_mod.ChatUnavailable as e:
        raise HTTPException(503, f"{e}. Start Ollama and pull the model, or use /tablemap/search.") from e
    except chat_mod.ChatBadOutput as e:
        raise HTTPException(502, f"{e}; try rephrasing the question") from e
    return {**asdict(out), "attribution": [*ATTRIBUTION, YELP_NOTICE]}
