# K04SPEND4 CODER_RETURN (OC-K04 copy)

STATUS: DONE (F1+F2+F3 PASS, no defects, no revert of product)

- STEP-0: math (9*0.1+358*0.2)/1e6 = 7.25e-05 executed; kept manager.py SPEND3V-WIP fail-loud logging, added /1e6; reverted bud1 refused-reserve test (502.000000 baked the bug; fixed cost 0.000502 fits 5.00).
- F1: /1_000_000 in manager.py `_charge_budget_gate` + run_store.py `record_provider_usage` (served-turn path). mr07b/spend01/spend3 1.600000->0.000002; bud1/bind3 4/6->4000/6000 usage, 0.016000->0.000016 (exact: (4000*0.001+6000*0.002)/1e6).
- Tests: required 3-file `10 passed in 8.18s`; extended 5-file (incl. bind3+spend01) `17 passed in 8.07s`.
- F2: stub_scan --files manager.py run_store.py exit 0, zero rows.
- F3 live (own harness 18773, urlpush keys=201 connect=200 meta ONLINE mock=False): chat 200, RAW tokens_total=828 MEASURED>0 AND RAW cost=8.51e-05 MEASURED>0 AND ledger same project ae86dea1 (3 rows); spent 0->0.000085. Server stopped, tmp/ deleted.
- NOT-DONE: budget/telemetry.py + telemetry/metrics.py CostCalculators untouched (quote/outage path, relative ordering unaffected, own pinned suites); no merge (HD commits).
