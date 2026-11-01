STATUS: DONE
files:
- src/agent_si/k10_compet.py — conflicts resolved per FACTS: docstring keeps
  K10 WAVE4+WAVE5 paragraphs; single served_rows() = union (34 rows: 16 int
  rows byte-identical + 18 K10 rows, no dup); all 40 K10-only defs kept
  (47 top-level defs total). Resolved-with-theirs == :3: bytes (asserted).
- tests/test_k10wave_served.py — unchanged (already the union: all 17 int
  tests present, 16 verbatim + bison_prior superseded by strict
  strengthening 16->34; 20 K10-only tests).
tests: D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe -m pytest -q
  -p no:cacheprovider tests/test_k10code_served.py tests/test_k10d_served.py
  tests/test_k10wave_served.py tests/local/test_iface_m1.py
tail: "83 passed in 27.08s" (first run, zero reds, no fix batch needed)
stub_scan --files src/agent_si/k10_compet.py tests/test_k10wave_served.py:
  clean (exit 0)
NOT-DONE: none
