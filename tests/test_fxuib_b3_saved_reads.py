# FXUIB-B3: saved chat-model / role-pool reads (RED first, then GREEN).
# Self-sufficient: portable sys.path bootstrap, no other lane's files needed.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

sys.path.insert(0, os.path.join(_HERE, "k04_lane_a"))
from test_pools_routes import make_ctx  # noqa: E402

from agent_si.backend import pools_routes as PR  # noqa: E402


def _save_chat(ctx, project_id, model_id):
    PR._save_chat_record(ctx.store, project_id, model_id)


def test_b3_get_chat_model_roundtrip(tmp_path):
    ctx = make_ctx(tmp_path)
    _save_chat(ctx, "p1", "openai/gpt-4o-mini")
    status, payload = PR.get_chat_model(ctx, {"project_id": "p1"}, None)
    assert status == 200, payload
    assert payload == {"project_id": "p1", "model_id": "openai/gpt-4o-mini"}


def test_b3_get_chat_model_missing(tmp_path):
    # Int FXSAVED semantics (single implementation kept): a missing record
    # reads 200 with model_id null, never 404; blank id stays 400.
    ctx = make_ctx(tmp_path)
    status, payload = PR.get_chat_model(ctx, {"project_id": "ghost"}, None)
    assert status == 200, payload
    assert payload == {"project_id": "ghost", "model_id": None}
    status, _ = PR.get_chat_model(ctx, {}, None)
    assert status == 400


def test_b3_get_role_pool_profile_roundtrip(tmp_path):
    ctx = make_ctx(tmp_path)
    status, _ = PR.put_role_pools(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "pool",
        "pool": [{"provider": "pa", "model": "pa/a-1",
                  "use_mode": "primary"}],
        "strategy": "FALLBACK_ORDER"})
    assert status == 200
    status, payload = PR.get_role_pool_profile(
        ctx, {"project_id": "p1", "role": "worker"}, None)
    assert status == 200, payload
    assert payload["role"] == "worker"
    assert payload["mode"] == "pool"
    assert payload["strategy"] == "FALLBACK_ORDER"
    assert [(m["provider_id"], m["model"]) for m in payload["pool"]] == [
        ("pa", "pa/a-1")]


def test_b3_get_role_pool_profile_missing(tmp_path):
    ctx = make_ctx(tmp_path)
    status, _ = PR.get_role_pool_profile(
        ctx, {"project_id": "ghost", "role": "worker"}, None)
    assert status == 404
    status, _ = PR.get_role_pool_profile(
        ctx, {"project_id": "p1", "role": "janitor"}, None)
    assert status == 400
    status, _ = PR.get_role_pool_profile(ctx, {}, None)
    assert status == 400


def test_b3_new_reads_are_served(tmp_path):
    ctx = make_ctx(tmp_path)
    assert ("get", "/api/v1/roles/chat-model") in PR._DISPATCH
    assert ("get", "/api/v1/roles/pools/profile") in PR._DISPATCH


def test_b6_empty_pool_put_refused_as_json(tmp_path):
    # FXUIB-B6 backend leg: PUT mode=pool pool=[] is refused 400 with a
    # JSON error body (never plain text, never a stored binding).
    ctx = make_ctx(tmp_path)
    status, payload = PR.put_role_pools(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "pool",
        "pool": [], "strategy": "AUTO"})
    assert status == 400, payload
    assert "at least one pool member" in payload["error"]
    status, payload = PR.get_role_pool_profile(
        ctx, {"project_id": "p1", "role": "worker"}, None)
    assert status == 404, payload
