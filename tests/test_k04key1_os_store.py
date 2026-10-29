import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402

from agent_si.providers.registry import facades as FAC  # noqa: E402
from agent_si.providers.registry.os_credential_store import (  # noqa: E402
    APP_NAMESPACE,
    OSCredentialStore,
)

BAIT = "FAKE-K04KEY1-OS-BAIT-2222-zzzz-not-a-real-key"

WIN = (os.name == "nt" and sys.platform == "win32")


def test_app_namespace_is_prefix():
    assert APP_NAMESPACE == "app:"
    store = OSCredentialStore(label_suffix="TEST")
    assert store._target("openai") == "app:openai:TEST"
    plain = OSCredentialStore()
    assert plain._target("openai") == "app:openai"
    assert BAIT not in repr(store)


def test_memory_store_value_port_roundtrip():
    _api, store, _sink = FAC.memory_stack()
    store.set_secret("s-k04key1", BAIT)
    assert store.has("s-k04key1") is True
    assert "s-k04key1" in store
    assert store.get_secret("s-k04key1") == BAIT
    assert store.get("s-k04key1") == BAIT
    assert store["s-k04key1"] == {"value": BAIT}
    assert BAIT not in repr(store)
    store.delete("s-k04key1")
    assert store.has("s-k04key1") is False
    with pytest.raises(KeyError):
        store.get_secret("s-k04key1")


@pytest.mark.skipif(not WIN, reason="Windows Credential Manager only")
def test_windows_os_store_write_delete_test_labelled():
    store = OSCredentialStore(label_suffix="TEST",
                              namespace=APP_NAMESPACE, timeout_s=5.0)
    secret_id = "k04key1-probe-%d" % (os.getpid(),)
    target = store._target(secret_id)
    assert target.startswith("app:")
    assert target.endswith(":TEST")
    try:
        store.set_secret(secret_id, BAIT)
        assert store.has(secret_id) is True
        assert store.get_secret(secret_id) == BAIT
        assert BAIT not in repr(store)
        store.delete(secret_id)
        assert store.has(secret_id) is False
        with pytest.raises(KeyError):
            store.get_secret(secret_id)
    finally:
        try:
            if store.has(secret_id):
                store.delete(secret_id)
        except Exception:
            pass
    assert store.has(secret_id) is False
