"""FXKBCHAT served proof: chat cites attached KB; attach never 500s.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over real tmp KB dirs on the real fs.
Unique project ids (proj-fxkbchat-*) keep the global KB registry
isolated from every other test file. Only the provider boundary uses
the sanctioned K04 MockProviderAdapter (no network, no keys).

  attached-KB chat cites retrieved sections incl the quokka probe fact.
  explicit kb_id is honored even when the project default differs.
  POST kb/attach with kind DEV_SHARED or a role-less body either
    succeeds per spec or answers an honest 4xx carrying a reason code.
  negatives: chat with no KB attached cites nothing;
    chat with an unknown kb_id answers an honest 404.
"""

import json
import os
import sys

import pytest
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

from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    build_bridge,
)
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import RunEvent  # noqa: E402
from src.agent_si.kb import registry as _registry  # noqa: E402
from src.agent_si.kb import retriever as _kb  # noqa: E402

TEST_TOKEN = "fxkbchat-token"
ACTOR = "coder-1-quokka"
CANNED = ("Canned service reply.",)

QUOKKA_SECTION = "quokka"
QUOKKA_FACT = "Quokka probe fact: quokkas nap in the shade after lunch."
NUMBAT_SECTION = "numbat"
NUMBAT_FACT = "Numbat probe fact: numbats patrol for termites at noon."


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _mock_adapter(canned=CANNED):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxkbchat-behavior",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _apply_chat_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxkbchat-test",
        "reason": "configure test project limits for chat behavior",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _write_kb_dir(path, sections, purpose="Fxkbchat notes."):
    path.mkdir(parents=True, exist_ok=True)
    (path / "sections").mkdir(exist_ok=True)
    for name, text in sections.items():
        (path / "sections" / ("%s.md" % name)).write_text(
            text, encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps({
            "kb_id": path.name,
            "purpose": purpose,
            "sections": sorted(sections),
        }),
        encoding="utf-8",
    )
    (path / "purpose.txt").write_text(purpose, encoding="utf-8")
    return str(path)


def _served_client(tmp_path, project_id, monkeypatch):
    """Real app with the orchestration path forced (manager loaders off)."""
    monkeypatch.setattr(
        _chat, "_load_manager_run_task_streamed", lambda: None)
    monkeypatch.setattr(
        _chat, "_load_manager_bound_provider", lambda: None)
    _apply_chat_limits(project_id)
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    return TestClient(app, raise_server_exceptions=False)


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _event_texts(text):
    return " ".join(
        str(event.get("text", ""))
        for event in _parse_sse(text)
        if isinstance(event, dict)
    )


def _attach(client, payload):
    return client.post(
        "/api/v1/kb/attach", json=payload, headers=_auth())


# -- attach: DEV_SHARED or role-less bodies never answer 500 -------------


def test_attach_dev_shared_role_less_accepted(tmp_path):
    project = "proj-fxkbchat-attach-shared"
    kb_id = _write_kb_dir(
        tmp_path / "kb-fxkbchat-shared",
        {"intro": "Shared intro notes."},
    )
    client = TestClient(
        create_app(_settings(tmp_path)), raise_server_exceptions=False)
    try:
        resp = _attach(client, {
            "kb_id": kb_id,
            "kind": "DEV_SHARED",
            "project_id": project,
            "purpose": "Shared notes.",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json() == kb_id
        assert _registry.is_attached(kb_id) is True
    finally:
        _kb.detach_kb(kb_id)


def test_attach_dev_role_role_less_accepted(tmp_path):
    project = "proj-fxkbchat-attach-role"
    kb_id = _write_kb_dir(
        tmp_path / "kb-fxkbchat-role",
        {"intro": "Role intro notes."},
    )
    client = TestClient(
        create_app(_settings(tmp_path)), raise_server_exceptions=False)
    try:
        resp = _attach(client, {"source": {
            "kb_id": kb_id,
            "kind": "DEV_ROLE",
            "project_id": project,
            "purpose": "Role notes.",
        }})
        assert resp.status_code == 200, resp.text
        assert resp.json() == kb_id
        assert _registry.is_attached(kb_id) is True
    finally:
        _kb.detach_kb(kb_id)


def test_attach_unknown_kind_honest_4xx(tmp_path):
    project = "proj-fxkbchat-attach-kind"
    kb_id = _write_kb_dir(
        tmp_path / "kb-fxkbchat-kind",
        {"intro": "Kind intro notes."},
    )
    client = TestClient(
        create_app(_settings(tmp_path)), raise_server_exceptions=False)
    try:
        resp = _attach(client, {"source": {
            "kb_id": kb_id,
            "kind": "NOPE",
            "project_id": project,
            "role": "dev",
            "purpose": "Kind notes.",
        }})
        assert resp.status_code != 500, resp.text
        assert 400 <= resp.status_code < 500, resp.text
        assert resp.json()["detail"].get("code"), resp.text
    finally:
        _kb.detach_kb(kb_id)


def test_attach_missing_purpose_honest_4xx(tmp_path):
    project = "proj-fxkbchat-attach-purpose"
    kb_id = _write_kb_dir(
        tmp_path / "kb-fxkbchat-purpose",
        {"intro": "Purpose intro notes."},
    )
    client = TestClient(
        create_app(_settings(tmp_path)), raise_server_exceptions=False)
    try:
        resp = _attach(client, {
            "kb_id": kb_id,
            "kind": "DEV_SHARED",
            "project_id": project,
        })
        assert resp.status_code != 500, resp.text
        assert 400 <= resp.status_code < 500, resp.text
        assert resp.json()["detail"].get("code"), resp.text
    finally:
        _kb.detach_kb(kb_id)


# -- chat cites the attached KB live -------------------------------------


def test_attached_kb_chat_cites_quokka(tmp_path, monkeypatch):
    project = "proj-fxkbchat-chat"
    kb_id = _write_kb_dir(
        tmp_path / "kb1",
        {QUOKKA_SECTION: QUOKKA_FACT},
    )
    client = _served_client(tmp_path, project, monkeypatch)
    try:
        attached = _attach(client, {"source": {
            "kb_id": kb_id,
            "kind": "DEV_SHARED",
            "project_id": project,
            "purpose": "Fxkbchat notes.",
        }})
        assert attached.status_code == 200, attached.text
        resp = client.post(
            "/api/v1/chat/stream",
            json={"project": project, "message": "quokka"},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        texts = _event_texts(resp.text)
        assert QUOKKA_FACT in texts
        assert ("#%s" % QUOKKA_SECTION) in texts
    finally:
        _kb.detach_kb(kb_id)


def test_explicit_kb_id_honored_over_project_default(
        tmp_path, monkeypatch):
    project = "proj-fxkbchat-explicit"
    other = "proj-fxkbchat-explicit-other"
    kb1 = _write_kb_dir(
        tmp_path / "kb1",
        {QUOKKA_SECTION: QUOKKA_FACT},
    )
    kb2 = _write_kb_dir(
        tmp_path / "kb2",
        {NUMBAT_SECTION: NUMBAT_FACT},
    )
    client = _served_client(tmp_path, project, monkeypatch)
    _apply_chat_limits(other)
    try:
        first = _attach(client, {"source": {
            "kb_id": kb1,
            "kind": "DEV_SHARED",
            "project_id": project,
            "purpose": "Fxkbchat notes.",
        }})
        assert first.status_code == 200, first.text
        second = _attach(client, {"source": {
            "kb_id": kb2,
            "kind": "DEV_SHARED",
            "project_id": other,
            "purpose": "Fxkbchat notes.",
        }})
        assert second.status_code == 200, second.text
        plain = client.post(
            "/api/v1/chat/stream",
            json={"project": project, "message": "numbat"},
            headers=_auth(),
        )
        assert plain.status_code == 200, plain.text
        assert ("#%s" % NUMBAT_SECTION) not in _event_texts(plain.text)
        explicit = client.post(
            "/api/v1/chat/stream",
            json={"project": project, "message": "numbat",
                  "kb_id": kb2},
            headers=_auth(),
        )
        assert explicit.status_code == 200, explicit.text
        texts = _event_texts(explicit.text)
        assert NUMBAT_FACT in texts
        assert ("#%s" % NUMBAT_SECTION) in texts
    finally:
        _kb.detach_kb(kb1)
        _kb.detach_kb(kb2)


# -- negatives hold -------------------------------------------------------


def test_chat_without_kb_cites_nothing(tmp_path, monkeypatch):
    project = "proj-fxkbchat-nokb"
    client = _served_client(tmp_path, project, monkeypatch)
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "message": "quokka"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    texts = _event_texts(resp.text)
    assert QUOKKA_FACT not in texts
    assert "#" not in texts
    assert "KB sources" not in texts


def test_chat_unknown_kb_id_honest_404(tmp_path, monkeypatch):
    project = "proj-fxkbchat-unknown"
    client = _served_client(tmp_path, project, monkeypatch)
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "message": "hello",
              "kb_id": "kb-missing-fxkbchat"},
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"].get("code"), resp.text


# -- manager path cites too (bridge level, injected manager run) ---------


def test_manager_path_cites_attached_kb(tmp_path):
    project = "proj-fxkbchat-manager"

    def _fake_run(request, **kwargs):
        yield RunEvent(
            event="start", turn=0, subtask_id="sub-001",
            detail="manager run started",
            data={"run_id": "run-fxkbchat-1"},
        )
        yield RunEvent(
            event="turn", turn=1, subtask_id="sub-001",
            detail="turn executed",
            data={"text": "manager says hi"},
        )
        yield RunEvent(
            event="done", turn=1, subtask_id="sub-001",
            detail="manager run finished",
            data={"executed": True},
        )

    kb_id = _write_kb_dir(
        tmp_path / "kb1",
        {QUOKKA_SECTION: QUOKKA_FACT},
    )
    try:
        _kb.attach_kb(_registry_sources(kb_id, project))
        bridge = build_bridge(
            provider_adapter=_mock_adapter(),
            run_task_streamed=_fake_run,
        )
        request = ChatStreamRequest.from_body(
            {"project": project, "message": "quokka"}, ACTOR)
        _stream_id, iterator = bridge.run(request)
        texts = " ".join(
            str(event.get("text", ""))
            for event in _parse_sse(
                b"".join(iterator).decode("utf-8"))
            if isinstance(event, dict)
        )
        assert QUOKKA_FACT in texts
        assert ("#%s" % QUOKKA_SECTION) in texts
    finally:
        _kb.detach_kb(kb_id)


def _registry_sources(kb_id, project):
    from src.agent_si.kb.models import KnowledgeSource

    return KnowledgeSource(
        kb_id=kb_id,
        kind="DEV_SHARED",
        project_id=project,
        role=None,
        purpose="Fxkbchat notes.",
    )
