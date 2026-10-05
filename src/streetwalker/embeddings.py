"""Text embeddings from a local Ollama server (decision 0024). Review text never leaves this machine.

Model: nomic-embed-text (137M parameters, Apache-2.0, 768 dimensions). It expects a task prefix: documents and queries are
embedded differently, so a question is compared with review text the way the model was trained to.
"""

import os
import re

import requests

MODEL = "nomic-embed-text"
DIM = 768
PREFIX = {"document": "search_document: ", "query": "search_query: "}
MAX_CHARS = 6000  # the server truncates at the model's context; this keeps requests small and predictable
BATCH = 32


class EmbeddingUnavailable(RuntimeError):
    pass


def _host() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return host if host.startswith("http") else f"http://{host}"


def model_id() -> str:
    """The model name and its digest, stored with every vector so a model change is visible."""
    try:
        tags = requests.get(f"{_host()}/api/tags", timeout=5).json()["models"]
    except (requests.RequestException, KeyError, ValueError) as e:
        raise EmbeddingUnavailable(f"cannot reach Ollama at {_host()}: {e}") from e
    for m in tags:
        if m["name"].split(":")[0] == MODEL:
            return f"{MODEL}@{m['digest'][:12]}"
    raise EmbeddingUnavailable(f"model {MODEL} is not installed (ollama pull {MODEL})")


def embed(texts: list[str], kind: str) -> list[list[float]]:
    """kind is 'document' or 'query'. Returns one vector per text."""
    if not texts:
        return []
    inputs = [PREFIX[kind] + t[:MAX_CHARS] for t in texts]
    try:
        r = requests.post(f"{_host()}/api/embed", json={"model": MODEL, "input": inputs, "keep_alive": "30m"}, timeout=300)
        r.raise_for_status()
        vecs = r.json()["embeddings"]
    except (requests.RequestException, KeyError, ValueError) as e:
        raise EmbeddingUnavailable(f"embedding request failed: {e}") from e
    if len(vecs) != len(texts) or any(len(v) != DIM for v in vecs):
        raise EmbeddingUnavailable("unexpected embedding shape")
    return vecs


def vec_literal(v: list[float]) -> str:
    """pgvector text form, bound as a parameter and cast with ::vector."""
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def dense_text(text: str) -> str:
    """The meaning part of a web-search style query: drop quotes, -excluded words and the OR operator before embedding."""
    t = re.sub(r"(^|\s)-\S+", " ", text.replace('"', " "))
    t = re.sub(r"\bor\b", " ", t, flags=re.IGNORECASE)
    return " ".join(t.split())
