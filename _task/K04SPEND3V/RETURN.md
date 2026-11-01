# K04SPEND3V RETURN (independent verification, OC-K04 copy)

STATUS: TESTS-GREEN + LIVE-RED (1 DEFECT, no product edits, no revert)

## Tree
- OC-K04 HEAD 3c3277a (contains c0ac0e1, FETCH_HEAD synced, tree was clean).
- K04B WIP exported (`git -C WT/K04B diff`, re-encoded UTF-16->UTF-8, same
  bytes) + `git apply` clean; untracked
  tests/test_k04spend3_persist_restart.py copied byte-identical
  (sha256 d7062e07...48e both sides). All 4 files == K04B WIP.
- 8773 harness is another team's (pid 5740/19136, unpatched int tree);
  untouched. Live run on own same-pattern harness from patched tree,
  loopback 18773, TEST suffix, own store/token (killed after).

## Tests (venv_agent_si pytest, tail)
- `test_k04bud1_budget_charge` 6 passed, `test_k04mr07b_spend_served`
  4 passed, `test_k04spend3_persist_restart` 1 passed.
- Tail: `11 passed in 6.29s` (incl.
  `test_priced_row_survives_cold_restart_and_charges PASSED`).

## Live "hi" (real Meta via gateway urlpush; key never printed)
- urlpush: keys=201 connect=200 meta ONLINE (2nd run: connect=400
  already-registered after restart rebind; key+connection persisted).
- Run1 (unpriced catalog): chat 200 real, tokens_total=435 MEASURED,
  cost UNAVAILABLE (no price) spent=0. Precondition missing, rerun seeded.
- Run2 (priced row bound at startup via product updater propose/apply +
  persist, owner MODEL_KB doc): chat 200 real ("Hi there! I'm Muse
  Spark..."), project d8bbd117, RAW ledger same project:
  cloud_calls=1 MEASURED, tokens_total=700 MEASURED,
  cost=72.50000000000001 USD MEASURED; budget spent="0" (limit 5.00).
- Harness stderr: `spend UNRECORDED: reserve refused ...
  (in=9 out=358 cost=72.500000) BudgetBlockedError: hard budget limit
  blocks ... requested 72.500000 USD would exceed hard 5.00 USD
  (spent 0, reserved 0) [BUDGET_HARD_BLOCKED] [MEASURED-spent]`.

## DEFECTS
- D-K04SPEND3V-01 | live chat, project d8bbd117 run 5bce9cca |
  RAW tokens_total=700 MEASURED + cost=72.5 MEASURED on same project
  vs budget.spent="0" | real "hi", default hard limit 5.00 |
  likely cause: per-token price math (9*0.1+358*0.2=72.5; mock bakes
  4*0.1+6*0.2=1.6) vs owner per-1M prices -> every real call exceeds
  the $5 hard limit -> gate refuses by design (loud, correct refusal)
  -> spent can never move live | OPEN (not reverted, not fixed by me).

## Notes
- TEST-suffixed OS credential entry left for HD cleanup (urlpush pattern).
- tmp/ (harness, logs, data, token) deleted after this write.
