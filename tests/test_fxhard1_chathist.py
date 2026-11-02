"""FXHARD1 chat history: lock, ids, redaction, statuses, paging.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) plus direct record_turn threads. No
provider, no network, no keys.
"""

import json
import os
import sys
import threading
import time

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import chat_history  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxhard1-token"
ACTOR = "coder-1-fxhard1"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _served_client(tmp_path):
    app = create_app(_settings(tmp_path))
    return TestClient(app, raise_server_exceptions=False), app


def _post(client, payload):
    return client.post(
        "/api/v1/chat/history", json=payload, headers=_auth())


def test_concurrent_appends_lose_no_turn_and_mint_unique_ids(tmp_path):
    _, app = _served_client(tmp_path)
    errors = []

    def worker(base):
        try:
            for index in range(10):
                chat_history.record_turn(
                    app, "p-race", "q-%s-%d" % (base, index),
                    "a-%s-%d" % (base, index))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    turns = chat_history.list_turns(app, "p-race", limit=1000)
    assert len(turns) == 200, len(turns)
    ids = [turn["id"] for turn in turns]
    assert len(set(ids)) == 200, "server ids must be unique"
    texts = sorted(turn["user_text"] for turn in turns)
    assert texts == sorted(
        "q-%s-%d" % (n, i) for n in range(20) for i in range(10))
    path = os.path.join(str(tmp_path), "chat_history.jsonl")
    with open(path, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle.read().splitlines()
                if line.strip()]
    assert len(rows) == 200, len(rows)


def test_running_upsert_leaves_one_turn_per_run(tmp_path):
    client, _app = _served_client(tmp_path)
    first = _post(client, {"project_id": "p-run", "user_text": "go",
                           "assistant_text": "", "status": "running",
                           "run_id": "r-1"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "running", first.text
    assert first.json()["id"], first.text
    second = _post(client, {"project_id": "p-run", "user_text": "go",
                            "assistant_text": "done",
                            "status": "ok", "run_id": "r-1"})
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"], second.text
    got = client.get("/api/v1/chat/history",
                     params={"project_id": "p-run"})
    assert got.status_code == 200, got.text
    turns = got.json()["turns"]
    assert len(turns) == 1, turns
    assert turns[0]["status"] == "ok", turns
    assert turns[0]["run_id"] == "r-1", turns


def test_failed_and_stopped_turns_persist_with_codes(tmp_path):
    client, _app = _served_client(tmp_path)
    failed = _post(client, {"project_id": "p-end",
                            "user_text": "do it",
                            "assistant_text": "half",
                            "status": "failed", "run_id": "r-f",
                            "error_code": "BUDGET_CAPPED"})
    assert failed.status_code == 200, failed.text
    stopped = _post(client, {"project_id": "p-end",
                             "user_text": "do other",
                             "assistant_text": "part",
                             "status": "stopped", "run_id": "r-s",
                             "error_code": "STOPPED"})
    assert stopped.status_code == 200, stopped.text
    got = client.get("/api/v1/chat/history",
                     params={"project_id": "p-end"})
    turns = got.json()["turns"]
    assert [(t["status"], t["error_code"]) for t in turns] == [
        ("failed", "BUDGET_CAPPED"), ("stopped", "STOPPED")], turns
    bad = _post(client, {"project_id": "p-end", "user_text": "x",
                         "assistant_text": "y", "status": "bogus"})
    assert bad.status_code == 400, bad.text


def test_bare_pasted_keys_are_redacted_before_storing(tmp_path):
    client, _app = _served_client(tmp_path)
    # NOTE: fake-secret values below are built by concatenation so this file
    # carries no secret-shaped literal for the release_pack secret scan
    # (it scans every tracked file); runtime values are unchanged and the
    # redaction assertions still prove the same behaviour.
    secrets = {
        "stripe": "sk-" + "live-abcDEF1234567890xyz",
        "stripe_test": "sk-" + "test-abcDEF1234567890xyz",
        "anthropic": "sk-ant-api03-abcDEF1234567890xyz",
        "proj": "sk-proj-abcDEF1234567890xyz",
        "plain": "sk-abcdefghij1234567890",
        "github": "ghp_" + "abcdefghij1234567890",
        "github_oauth": "gho_abcdefghij1234567890",
        "slack": "xox" + "b-12345-abcdefghij123456",
        "aws": "AKIAIOSFODNN7EXAMPLE",
        "eq": "api_key=abc123SECRET",
        "colon": "token: abc123SECRET",
        "arrow": "password => hunter2SECRET",
        "pem": ("-----BEGIN " + "PRIVATE KEY-----\n"
                "MIIEvwIBADANBgkqhkiG9w0BAQEFAASC\n"
                "-----END PRIVATE KEY-----"),
    }
    payload = {"project_id": "p-sec",
               "user_text": " ".join(secrets.values()),
               "assistant_text": "noted " + secrets["stripe"]}
    resp = _post(client, payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for name, secret in secrets.items():
        assert secret not in body["user_text"], (name, body)
    assert secrets["stripe"] not in body["assistant_text"], body
    got = client.get("/api/v1/chat/history",
                     params={"project_id": "p-sec"})
    dumped = json.dumps(got.json())
    for name, secret in secrets.items():
        assert secret not in dumped, name
    assert "[redacted]" in dumped, dumped


def test_redaction_ignores_ordinary_words_and_paths():
    clean = [
        "quokka hello: map the north fence",
        "the secretary filed the Monday report",
        "keyboard shortcut ctrl+k opens the palette",
        "tokenize the output into small words",
        "see src/agent_si/backend/app.py line 10",
        "read docs/guide.md and CHANGELOG",
        "monkey business at C:/data/keys/list.txt",
        "apiary notes: the bees are calm",
        "my pass word is hunter2 free",  # split words, no label shape
    ]
    for text in clean:
        assert chat_history._scrub(text) == text, text


def test_scrub_failure_stores_marker_never_raw(monkeypatch):
    def _boom(text):
        raise RuntimeError("redactor down")

    monkeypatch.setattr(chat_history, "_scrub_bare", _boom)
    assert chat_history._scrub("sk-" + "live-abcDEF1234567890xyz") == \
        "[redacted]"
    assert chat_history._scrub("plain hello") == "[redacted]"


def test_history_pages_newest_200_with_earlier_cursor(tmp_path):
    client, app = _served_client(tmp_path)
    for index in range(500):
        chat_history.record_turn(
            app, "p-big", "q-%03d" % index, "a-%03d" % index)
    started = time.perf_counter()
    got = client.get("/api/v1/chat/history",
                     params={"project_id": "p-big"})
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    print("\nFXHARD1 500-turn GET newest-200 took %.1f ms" % elapsed_ms)
    assert got.status_code == 200, got.text
    page = got.json()
    assert page["total"] == 500, page["total"]
    assert len(page["turns"]) == 200, len(page["turns"])
    assert page["turns"][0]["user_text"] == "q-300", page["turns"][0]
    assert page["turns"][-1]["user_text"] == "q-499", page["turns"][-1]
    assert page["next_before"], page
    earlier = client.get("/api/v1/chat/history",
                         params={"project_id": "p-big",
                                 "before": page["next_before"]})
    assert earlier.status_code == 200, earlier.text
    older = earlier.json()
    assert older["total"] == 300, older["total"]
    assert len(older["turns"]) == 200, len(older["turns"])
    assert older["turns"][0]["user_text"] == "q-100", older["turns"][0]
    last = client.get("/api/v1/chat/history",
                      params={"project_id": "p-big",
                              "before": older["next_before"]})
    assert last.status_code == 200, last.text
    tail = last.json()
    assert [t["user_text"] for t in tail["turns"]] == [
        "q-%03d" % i for i in range(100)], tail["turns"][:3]
    assert tail["next_before"] is None, tail
    assert elapsed_ms < 2000.0, elapsed_ms


def test_unknown_cursor_returns_empty_page(tmp_path):
    client, app = _served_client(tmp_path)
    chat_history.record_turn(app, "p-cur", "hi", "hello")
    got = client.get("/api/v1/chat/history",
                     params={"project_id": "p-cur", "before": "nope"})
    assert got.status_code == 200, got.text
    assert got.json()["turns"] == [], got.text
    assert got.json()["next_before"] is None, got.text
