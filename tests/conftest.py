"""S4: no test run may touch the real OS key store.

Every pytest worker imports this file first, so the documented product
setting defaults to the memory store for the whole session unless a
test explicitly opts out. Tests that assert the OS default clear the
variable with ``monkeypatch.delenv("AGENT_SI_SECRET_STORE")`` and keep
passing against the real default below.
"""
import os

os.environ.setdefault("AGENT_SI_SECRET_STORE", "memory")
