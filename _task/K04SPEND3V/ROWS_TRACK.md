# K04SPEND3V ROWS_TRACK (coverage rows -> file + test -> verdict)

- F1 priced KB row persists + rebinds on cold restart:
  tests/test_k04spend3_persist_restart.py (fresh interpreter, same store)
  -> REAL, PASS.
- F2 served priced hi charges spent + MEASURED cost row:
  tests/test_k04mr07b_spend_served.py + tests/test_k04bud1_budget_charge.py
  (mock transport) -> REAL, PASS (7 tests);
  LIVE (real Meta, run2): cost=72.5 MEASURED but budget.spent=0
  (gate refusal over $5 hard limit) -> RED, see D-K04SPEND3V-01.
- F3 ledger rows on SAME chat project (tokens_total + cost, MEASURED):
  tmp store run2: 700 MEASURED + 72.5 MEASURED, project d8bbd117
  -> REAL, PASS (mock: 11-pass suite; live: RAW rows present).

FAKE 0, MISSING 0. No VERDICT (fresh auditor follows).
