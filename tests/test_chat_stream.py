"""The streaming chat endpoint and cancellation (decision 0032). Everything here is invented and runs without Ollama or Postgres: the model is a
scripted fake, and the questions are out of scope so that no search runs. A real server on a local port is used for the disconnect test, since that
is the only way to see a client leave."""

import json
import socket
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from streetwalker import chat, tablemap_api
from streetwalker.aspects import ASPECTS
from streetwalker.deps import get_conn

OUT_OF_SCOPE_PLAN = {"in_scope": False, "topic": "", "kinds": [], "area": "any", **dict.fromkeys(ASPECTS, "any"), "near_rail": False, "sort": "relevance"}


class Quick:
    name = "quick"

    def generate(self, messages, schema):
        return dict(OUT_OF_SCOPE_PLAN)


class Waits:
    """A model that never finishes by itself: it notices a cancel the way OllamaChat does between tokens (chat.check_cancel)."""

    name = "waits"

    def __init__(self):
        self.started, self.stopped = threading.Event(), threading.Event()

    def generate(self, messages, schema):
        self.started.set()
        try:
            while True:
                chat.check_cancel()
                time.sleep(0.02)
        finally:
            self.stopped.set()


class Down:
    name = "down"

    def generate(self, messages, schema):
        raise chat.ChatUnavailable("no server")


def make_app(backend) -> FastAPI:
    app = FastAPI()
    app.include_router(tablemap_api.router)
    app.dependency_overrides[get_conn] = lambda: None  # the questions below never reach the database
    app.dependency_overrides[tablemap_api.get_chat_backend] = lambda: backend
    return app


def events_of(response) -> list[dict]:
    return [json.loads(line) for line in response.iter_lines() if line.strip()]


def test_the_stream_sends_stage_events_then_the_same_answer_the_json_endpoint_returns():
    client = TestClient(make_app(Quick()))
    body = {"question": "What is the capital of France?"}
    with client.stream("POST", "/tablemap/chat/stream", json=body) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
        evs = events_of(r)
    assert evs[0] == {"event": "stage", "stage": "plan", "text": "Working out what to search for"}
    assert [e["event"] for e in evs] == ["stage", "answer"]
    assert evs[-1]["data"] == client.post("/tablemap/chat", json=body).json()  # nothing is added or left out by streaming


def test_a_model_failure_ends_the_stream_with_an_error_event_carrying_the_status_the_json_endpoint_uses():
    client = TestClient(make_app(Down()))
    with client.stream("POST", "/tablemap/chat/stream", json={"question": "hello there"}) as r:
        last = events_of(r)[-1]
    assert last["event"] == "error" and last["status"] == 503 and "no server" in last["detail"]
    assert client.post("/tablemap/chat", json={"question": "hello there"}).status_code == 503


def test_input_is_validated_before_the_stream_starts():
    client = TestClient(make_app(Quick()))
    assert client.post("/tablemap/chat/stream", json={"question": ""}).status_code == 422
    assert client.post("/tablemap/chat/stream", json={"question": "x", "style": "poem"}).status_code == 422


def test_check_cancel_and_note_do_nothing_unless_a_listener_is_set():
    chat.check_cancel()
    chat.note(stage="plan")  # no listener: no error
    flag, seen = threading.Event(), []
    with chat.listening(seen.append, flag):
        chat.note(stage="plan", text="x")
        flag.set()
        with pytest.raises(chat.Cancelled):
            chat.check_cancel()
    assert seen == [{"event": "stage", "stage": "plan", "text": "x"}]
    chat.check_cancel()  # the flag is not left behind


def test_a_broken_listener_cannot_break_an_answer():
    def boom(event):
        raise RuntimeError("listener failed")

    with chat.listening(boom, None):
        out = chat.answer(None, Quick(), "What is the capital of France?", lambda *a: None)
    assert out.in_scope is False


def test_a_cancel_between_steps_stops_before_the_next_step():
    flag = threading.Event()

    class CancelsAfterPlan(Quick):
        def generate(self, messages, schema):
            out = super().generate(messages, schema)
            out["in_scope"] = True  # so that the search step would come next
            flag.set()
            return out

    searched = []
    with chat.listening(None, flag), pytest.raises(chat.Cancelled):
        chat.answer(None, CancelsAfterPlan(), "quiet cafes", lambda *a: searched.append(a))
    assert searched == []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def live(app):
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)


def test_a_client_that_leaves_stops_the_model():
    backend = Waits()
    with live(make_app(backend)) as url, httpx.Client(timeout=10) as client:
        with client.stream("POST", f"{url}/tablemap/chat/stream", json={"question": "quiet cafes"}) as r:
            first = next(line for line in r.iter_lines() if line.strip())
            assert json.loads(first)["event"] == "stage"
            assert backend.started.wait(5)
        # leaving the `with` closes the connection: the server must notice, set the flag, and the model's loop must end
        assert backend.stopped.wait(5), "the model kept running after the client left"


def test_the_whole_stream_works_through_a_real_server_too():
    with live(make_app(Quick())) as url, httpx.Client(timeout=10) as client, client.stream(
        "POST", f"{url}/tablemap/chat/stream", json={"question": "What is the capital of France?"}
    ) as r:
        evs = events_of(r)
    assert evs[-1]["event"] == "answer" and evs[-1]["data"]["in_scope"] is False


# ---- the streamed Ollama call, against a stub server speaking its protocol --------------------------------------------------

@contextmanager
def stub_ollama(monkeypatch, handler_lines, closed: threading.Event):
    """A local server that answers /api/chat with the given NDJSON lines, slowly, and records when the client hangs up."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            try:
                for line in handler_lines:
                    self.wfile.write((line + "\n").encode())
                    self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                closed.set()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{srv.server_address[1]}")
    try:
        yield
    finally:
        srv.shutdown()


def chunk(text: str, done: bool = False) -> str:
    return json.dumps({"message": {"role": "assistant", "content": text}, "done": done})


def test_the_streamed_reply_is_put_back_together_and_parsed(monkeypatch):
    lines = [chunk('{"answers"'), chunk(": tr"), chunk("ue}"), chunk("", True)]
    with stub_ollama(monkeypatch, lines, threading.Event()):
        assert chat.OllamaChat("m").generate([{"role": "user", "content": "x"}], chat.VERIFY_SCHEMA) == {"answers": True}


def test_an_error_line_an_empty_reply_and_non_json_are_reported_as_before(monkeypatch):
    ask = lambda: chat.OllamaChat("m").generate([], chat.VERIFY_SCHEMA)
    with stub_ollama(monkeypatch, [json.dumps({"error": "model not found"})], threading.Event()), pytest.raises(chat.ChatUnavailable, match="model not found"):
        ask()
    with stub_ollama(monkeypatch, [chunk("", True)], threading.Event()), pytest.raises(chat.ChatUnavailable, match="empty reply"):
        ask()
    with stub_ollama(monkeypatch, [chunk("not json"), chunk("", True)], threading.Event()), pytest.raises(chat.ChatBadOutput):
        ask()


def test_a_cancel_mid_reply_hangs_up_on_the_model(monkeypatch):
    closed, flag = threading.Event(), threading.Event()
    lines = [chunk('{"a')] + [chunk("x")] * 400 + [chunk("", True)]  # about 20 s of output if nobody stops it
    started = time.time()
    with stub_ollama(monkeypatch, lines, closed):
        threading.Timer(0.3, flag.set).start()
        with chat.listening(None, flag), pytest.raises(chat.Cancelled):
            chat.OllamaChat("m").generate([], chat.VERIFY_SCHEMA)
        assert closed.wait(5), "the stub never saw the client hang up"
    assert time.time() - started < 5
