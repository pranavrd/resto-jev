"""Thin wrapper around the TypeSafe SDK: one request per building, parsed into plain records."""

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient, TypeSafeError

from streetwalker.db import ROOT
from streetwalker.jev_questions import MODEL_VERSION, build_questions


@dataclass(frozen=True)
class Answer:
    question: str
    answer: str | None
    probs: dict | None
    confidence: float | None


@dataclass(frozen=True)
class Result:
    answers: list[Answer]
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    model: str | None
    error: str | None = None


def make_client() -> TypeSafeClient:
    """The key lives in .env as JEV_API_KEY; the SDK's own variable is TYPESAFE_API_KEY. Either works.
    The value is passed straight to the client and never printed or logged."""
    load_dotenv(ROOT / ".env")
    key = os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("Set JEV_API_KEY in .env")
    return TypeSafeClient(api_key=key, model=MODEL_VERSION)


def parse(response) -> list[Answer]:
    """Normalise a SystemOneResponse. Yes/no answers become answer 'true'/'false' with confidence max(p, 1-p)."""
    out = []
    for name, a in response.answers.items():
        if a.type == "choice":
            out.append(Answer(name, a.choice, dict(a.probabilities), a.confidence))
        elif a.type == "noul":
            out.append(Answer(name, "true" if a.noul >= 0.5 else "false", {"yes": a.noul}, max(a.noul, 1 - a.noul)))
    return out


def ask(client: TypeSafeClient, state, questions: dict | None = None) -> Result:
    t0 = time.perf_counter()
    try:
        resp = client.system_one(state=state, questions=questions or build_questions())
    except TypeSafeError as e:
        return Result([], None, None, int((time.perf_counter() - t0) * 1000), None, f"{type(e).__name__}: {e}"[:300])
    ms = int((time.perf_counter() - t0) * 1000)
    return Result(parse(resp), resp.usage.input_tokens, resp.usage.output_tokens, ms, resp.model)
