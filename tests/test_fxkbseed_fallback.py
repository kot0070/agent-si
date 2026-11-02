"""FXKBSEED: seed rows for meta+anthropic, persist backfill, AUTO fallback.

K1: SEED_CATALOG holds ("meta","muse-spark-1.3-contributor") and
    ("anthropic","claude-haiku-4-5") with every field UNKNOWN.
K2: load_persisted adds missing seed rows; present rows never overwritten.
K3: roles._auto_pick with no KB row for a connected provider falls back
    to that provider's first enabled facade model with the honest why;
    any other block stays a RoleUnbound run-failed line.
K4: fresh seed + only meta connected -> all 4 roles resolve to
    meta/muse-spark-1.3-contributor; fake-provider run reaches Director;
    unknown price -> cost UNKNOWN, no crash, no cap false stop.
"""
import copy
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.model_kb import kb


def _pairs(catalog):
    return [(row.get("provider_id"), row.get("model_id"))
            for row in catalog.get("models", [])]


# --- K1: seed rows ----------------------------------------------------------


def test_seed_holds_meta_and_anthropic_rows():
    pairs = _pairs(kb.SEED_CATALOG)
    assert ("meta", "muse-spark-1.3-contributor") in pairs
    assert ("anthropic", "claude-haiku-4-5") in pairs


def test_seed_rows_are_honest_unknown():
    wanted = {("meta", "muse-spark-1.3-contributor"),
              ("anthropic", "claude-haiku-4-5")}
    for row in kb.SEED_CATALOG["models"]:
        if (row.get("provider_id"), row.get("model_id")) in wanted:
            for name, field in row["fields"].items():
                assert field == {"value": "UNKNOWN", "source": "UNKNOWN",
                                 "retrieved_at": "UNKNOWN"}, (row, name)
    assert kb.validate_catalog(kb.SEED_CATALOG) == []


# --- K2: persist backfill ----------------------------------------------------


def test_persisted_catalog_gains_missing_seed_rows(tmp_path):
    old_dir = kb._PERSIST_DIR
    old_bound = copy.deepcopy(kb._BOUND_CATALOG)
    kb.set_persist_dir(str(tmp_path))
    try:
        enriched = kb.make_model_row("openai", "gpt-4o", {
            "purpose": kb.sourced("flagship chat", "https://example.com/x",
                                  "2026-10-01")})
        catalog = kb.make_catalog(
            [enriched, kb.make_model_row("openai", "gpt-4o-mini")])
        kb.save_catalog(catalog, kb.persist_path())
        kb._BOUND_CATALOG = None
        bound = kb.load_persisted()
        pairs = _pairs(bound)
        assert ("meta", "muse-spark-1.3-contributor") in pairs
        assert ("anthropic", "claude-haiku-4-5") in pairs
        kept = [row for row in bound["models"]
                if (row.get("provider_id"), row.get("model_id"))
                == ("openai", "gpt-4o")][0]
        assert kept["fields"]["purpose"]["value"] == "flagship chat"
        assert kept["fields"]["purpose"]["source"] == "https://example.com/x"
        assert kb.validate_catalog(bound) == []
    finally:
        kb._PERSIST_DIR = old_dir
        kb._BOUND_CATALOG = old_bound


# --- K3/K4: AUTO fallback doubles --------------------------------------------


class _View:
    def __init__(self, provider_id, evidenced=True):
        self.provider_id = provider_id
        self.evidenced = evidenced


class _Facade:
    def __init__(self, models_by_provider, evidenced=()):
        self._providers = {
            provider: {"models": dict(models)}
            for provider, models in models_by_provider.items()
        }
        self._evidenced = list(evidenced or models_by_provider.keys())

    def list_providers(self, only_evidenced=False):
        return [_View(pid, True) for pid in self._evidenced]


class _Table:
    def get_profile(self, project_id, role):
        return None


def _app(facade):
    ctx = types.SimpleNamespace(store=None, provider_facade=facade,
                                role_table=_Table())
    return types.SimpleNamespace(state=types.SimpleNamespace(k04_ctx=ctx))


def _with_seed():
    from agent_si.model_kb import kb as _kb
    previous = _kb._BOUND_CATALOG
    _kb.bind_catalog(copy.deepcopy(_kb.SEED_CATALOG))
    return previous


def test_all_roles_resolve_to_meta_on_fresh_seed():
    from agent_si.model_kb import kb as _kb
    from agent_si.runtime.devrun import roles as _roles
    previous = _with_seed()
    try:
        facade = _Facade({"meta": {"default": "muse-spark-1.3-contributor"}})
        app = _app(facade)
        for role in ("director", "manager", "worker", "auditor"):
            got = _roles.resolve_role(app, "p-fresh", role)
            assert got["provider"] == "meta", got
            assert got["model"] == "muse-spark-1.3-contributor", got
    finally:
        _kb._BOUND_CATALOG = previous


def test_no_kb_row_falls_back_to_first_facade_model():
    from agent_si.model_kb import kb as _kb
    from agent_si.runtime.devrun import roles as _roles
    previous = _with_seed()
    try:
        facade = _Facade({"fakep": {"default": "fakep-model"}})
        app = _app(facade)
        got = _roles.resolve_role(app, "p-fake", "director")
        assert got["provider"] == "fakep", got
        assert got["model"] == "fakep-model", got
        assert "no KB row: first enabled model of the connected " \
            "provider" in str(got.get("why", {}).get("reason", "")), got
    finally:
        _kb._BOUND_CATALOG = previous


def test_other_blocks_stay_run_failed():
    from agent_si.model_kb import kb as _kb
    from agent_si.runtime.devrun import roles as _roles
    previous = _with_seed()
    try:
        facade = _Facade({}, evidenced=[])
        app = _app(facade)
        try:
            _roles.resolve_role(app, "p-none", "director")
        except _roles.RoleUnbound as exc:
            assert "no provider" in str(exc).lower() or \
                "AUTO pick failed" in str(exc), str(exc)
        else:
            raise AssertionError("empty connected set resolved")
    finally:
        _kb._BOUND_CATALOG = previous


def test_unknown_price_never_crashes_nor_cap_stops():
    from agent_si.model_kb import kb as _kb
    from agent_si.backend import routing_auto as _auto
    from agent_si.runtime.devrun import roles as _roles
    from agent_si.runtime import manager as _manager
    previous = _with_seed()
    try:
        catalog = _kb.bound_catalog()
        ranked = _auto._cheapest_first(
            [{"row": row} for row in catalog["models"]])
        assert ranked, "seed candidates rank without crashing"
        inp, outp = _manager._kb_price_for_manager(
            "meta", "muse-spark-1.3-contributor")
        assert (inp, outp) == (None, None)
        facade = _Facade({"meta": {"default": "muse-spark-1.3-contributor"}})
        app = _app(facade)
        assert _roles._over_cap(
            app, "p-fresh", "meta", "muse-spark-1.3-contributor",
            {"input_tokens": 1000000,
             "output_tokens": 1000000}) is False
        assert _roles._cap_block(
            app, "p-fresh", "meta") is None
    finally:
        _kb._BOUND_CATALOG = previous
