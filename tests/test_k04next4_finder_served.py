"""K04NEXT4-B finder proofs (CODER-B seam): leftover-key finder M-P4-144..148.

Live E2E through create_app + TestClient over real modules only: the
finder GET plus DELETE rows on ``/api/v1/providers/leftover-keys`` are
bound by importing :mod:`agent_si.pools.leftover` BEFORE create_app
registers routes (the import must stay at the top of this module). No
mocks for the claim; loopback TestClient only. One row per test with
the verbatim rule plus code.

M-P4-145 note: the served memory credential store keeps mapping seeds
opaque to mapping reads (``store[name]`` raises KeyError for dict
seeds), so dates are proven at the seam level here through the lane's
own read-view port (a plain name-to-mapping view, exactly what
ProviderCtx documents); the served GET half proves names plus
exclusion plus missing-entry NOT_FOUND with the served store.
"""
import sys
import types
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent_si.pools.leftover as LEFTOVER_SEAM

_FINDER = "/api/v1/providers/leftover-keys"

_HDRS = {"x-actor": "ui-next4", "x-ui-session-token": "ui-next4"}


def _client(tmp_path):
    from agent_si.backend.app import create_app
    import fastapi.testclient

    app = create_app(
        {"store_dir": str(tmp_path / "appdata"), "secret_store": "memory"},
        auth_hook=None,
        rate_hook=None,
        model_factory=None,
    )
    return fastapi.testclient.TestClient(app)


def _delete(client, url, payload, headers):
    """DELETE with a JSON body (the finder delete contract)."""
    return client.request("DELETE", url, json=payload, headers=headers)


def _seam_ctx(store_view=None, store=None, live_ids=(), audit=None):
    """Minimal served-context double: plain port attributes only."""
    sink = audit if audit is not None else []
    if not hasattr(sink, "append"):
        raise AssertionError("audit double needs append")
    view = {} if store_view is None else store_view
    return types.SimpleNamespace(
        provider_facade=None,
        app_prefix=None,
        store_view=view,
        store=view if store is None else store,
        audit_sink=sink,
        live_provider_ids=tuple(live_ids),
        session_token="",
        ui_session_token="",
    )


# M-P4-144: leftover-key finder lists product-prefixed entries; user-click delete.
def test_m_p4_144_finder_delete_outside_prefix_refused_served(tmp_path):
    """Row M-P4-144: deleting an entry outside the app prefix refuses
    with NOT_OWN_PREFIX (CODER-B seam)."""
    client = _client(tmp_path)
    resp = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "other:key",
         "confirmed": True, "session_token": "tok-next4"},
        _HDRS)
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body.get("code") == "NOT_OWN_PREFIX", body
    assert body.get("rule") == "M-P4-144", body


# M-P4-145: finder shows names plus dates only; never touches others.
def test_m_p4_145_finder_names_only_missing_not_found_served(tmp_path):
    """Row M-P4-145 (served half): the list shows only own-prefix names
    and deleting a missing entry refuses NOT_FOUND; others untouched."""
    client = _client(tmp_path)
    ctx = client.app.state.k04_ctx
    ctx.credential_store.seed("app:next4-one", "leftover-value-one")
    ctx.credential_store.seed("other:key", "leftover-value-other")
    listed = client.get(_FINDER, params={"app_prefix": "app:"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["entries"] == [
        {"name": "app:next4-one", "last_used_at": ""}], listed.text
    missing = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "app:next4-gone",
         "confirmed": True, "session_token": "tok-next4"},
        _HDRS)
    assert missing.status_code == 404, missing.text
    assert missing.json().get("code") == "NOT_FOUND", missing.text
    assert missing.json().get("rule") == "M-P4-145", missing.text
    assert ctx.credential_store.has("app:next4-one")
    assert ctx.credential_store.has("other:key")


def test_m_p4_145_finder_dates_only_projection_seam():
    """Row M-P4-145 (dates half): through the seam's bound read view an
    entry projects to name plus last_used_at only; secret fields never
    surface and foreign entries are excluded without being touched."""
    store = {
        "app:one": {"last_used_at": "2026-10-26",
                    "token": "must-strip"},
        "other:key": {"last_used_at": "2026-10-26"},
    }
    audit = []
    ctx = _seam_ctx(store_view=store, audit=audit)
    status, payload = LEFTOVER_SEAM.leftover_keys_served(
        ctx, {"app_prefix": "app:"}, None)
    assert status == 200, payload
    assert payload["entries"] == [
        {"name": "app:one", "last_used_at": "2026-10-26"}], payload
    assert store["app:one"] == {"last_used_at": "2026-10-26",
                                "token": "must-strip"}, store
    assert store["other:key"] == {"last_used_at": "2026-10-26"}, store
    assert audit == [], audit


# M-P4-146: live-provider-linked entry never deletable.
def test_m_p4_146_finder_live_linked_never_deletable_served(tmp_path):
    """Row M-P4-146: deleting a live-provider-linked entry refuses with
    LIVE_LINKED (CODER-B seam)."""
    client = _client(tmp_path)
    saved = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "lm-studio", "key_value": "k-next4-146"},
        headers=_HDRS)
    assert saved.status_code == 201, saved.text
    connected = client.post(
        "/api/v1/providers/connect",
        json={"preset_id": "lm-studio", "model": "m-next4-146",
              "key_ref": {"secret_id": "lm-studio",
                         "provider_id": "lm-studio"}},
        headers=_HDRS)
    assert connected.status_code == 200, connected.text
    providers = client.get("/api/v1/providers", headers=_HDRS)
    assert providers.status_code == 200, providers.text
    assert "lm-studio" in [
        row["provider_id"] for row in providers.json()["providers"]]
    ctx = client.app.state.k04_ctx
    ctx.credential_store.seed(
        "app:lm-studio", {"last_used_at": "2026-10-26"})
    refused = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "app:lm-studio",
         "confirmed": True, "session_token": "tok-next4"},
        _HDRS)
    assert refused.status_code == 409, refused.text
    assert refused.json().get("code") == "LIVE_LINKED", refused.text
    assert refused.json().get("rule") == "M-P4-146", refused.text
    assert ctx.credential_store.has("app:lm-studio")


# M-P4-147: explicit confirm per entry and behind session token.
def test_m_p4_147_finder_confirm_and_token_required_served(tmp_path):
    """Row M-P4-147: per-entry delete needs explicit confirm plus a
    session token, then removes exactly that entry (CODER-B seam)."""
    client = _client(tmp_path)
    ctx = client.app.state.k04_ctx
    ctx.credential_store.seed("app:next4-seven", "leftover-value-seven")
    no_confirm = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "app:next4-seven",
         "session_token": "tok-next4"},
        _HDRS)
    assert no_confirm.status_code == 400, no_confirm.text
    assert no_confirm.json().get("code") == "CONFIRM_REQUIRED", no_confirm.text
    assert no_confirm.json().get("rule") == "M-P4-147", no_confirm.text
    no_token = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "app:next4-seven",
         "confirmed": True},
        _HDRS)
    assert no_token.status_code == 401, no_token.text
    assert no_token.json().get("code") == "TOKEN_REQUIRED", no_token.text
    assert no_token.json().get("rule") == "M-P4-147", no_token.text
    removed = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "app:next4-seven",
         "confirmed": True, "session_token": "tok-next4"},
        _HDRS)
    assert removed.status_code == 200, removed.text
    assert removed.json().get("removed") is True, removed.text
    assert not ctx.credential_store.has("app:next4-seven")


def test_m_p4_147_served_bind_never_reads_ctx_token():
    """Row M-P4-147 (seam pin): the per-entry token comes from served
    params only; a context/header handle never authorizes a delete, so
    TOKEN_REQUIRED stays reachable over HTTP."""
    from agent_si.adapters import leftover_access as access

    merged = access.bind_served_params({"app_prefix": "app:"}, None)
    assert "session_token" not in merged, merged
    assert "token" not in merged, merged
    explicit = access.bind_served_params(
        {"session_token": "tok-next4"}, {"app_prefix": "app:"})
    assert explicit["session_token"] == "tok-next4", explicit
    ctx = _seam_ctx(
        store_view={"app:seven": {"last_used_at": "2026-10-26"}})
    ctx.session_token = "header-handle"
    status, payload = LEFTOVER_SEAM.leftover_keys_served(
        ctx, {"app_prefix": "app:", "name": "app:seven",
              "confirmed": True}, None)
    assert status == 401, payload
    assert payload.get("code") == "TOKEN_REQUIRED", payload
    assert payload.get("rule") == "M-P4-147", payload


# M-P4-148: credential deletion audit-logged by entry name; real reasons.
def test_m_p4_148_finder_delete_audit_logged_by_name_served(tmp_path):
    """Row M-P4-148: a confirmed delete is audit-logged by entry name
    with the real reason (CODER-B seam)."""
    client = _client(tmp_path)
    ctx = client.app.state.k04_ctx
    ctx.credential_store.seed("app:next4-eight", "leftover-value-eight")
    removed = _delete(
        client, _FINDER,
        {"app_prefix": "app:", "name": "app:next4-eight",
         "confirmed": True, "session_token": "tok-next4",
         "reason": "user-confirmed-cleanup"},
        _HDRS)
    assert removed.status_code == 200, removed.text
    assert removed.json().get("removed") is True, removed.text
    records = [rec for rec in ctx.audit_sink.records
               if rec.get("entry") == "app:next4-eight"]
    assert len(records) == 1, ctx.audit_sink.records
    assert records[0]["reason"] == "user-confirmed-cleanup", records[0]
    assert records[0]["at"], records[0]


def test_finder_rows_bound_in_served_tables():
    """Seam evidence: GET plus DELETE on the finder route serve the
    bound CODER-B handler (no bare pre-merge mirror)."""
    from agent_si.backend import pools_routes as PR

    assert PR._DISPATCH[("get", _FINDER)] is LEFTOVER_SEAM.leftover_keys_served
    assert PR._DISPATCH[("delete", _FINDER)] is LEFTOVER_SEAM.leftover_keys_served
    legacy = {(str(method).lower(), str(path), str(name))
              for method, path, name, _fn in PR._LEGACY_ROUTES
              if str(path) == _FINDER}
    assert ("get", _FINDER, "leftover_keys") in legacy, legacy
    assert ("delete", _FINDER, "leftover_keys_delete") in legacy, legacy


def test_m_p4_145_finder_mapping_payload_last_used_at_served(tmp_path):
    """Row M-P4-145 (served mapping half): a served memory store entry
    seeded with a mapping payload projects last_used_at on the finder."""
    client = _client(tmp_path)
    ctx = client.app.state.k04_ctx
    ctx.credential_store.seed(
        "app:next4-map", {"last_used_at": "2026-10-26"})
    listed = client.get(_FINDER, params={"app_prefix": "app:"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["entries"] == [
        {"name": "app:next4-map", "last_used_at": "2026-10-26"}], listed.text
