AGENT: CODER-1 K04SPEND4 (OpenCode PAIR, background ses_e6b2a7744)
# CODER-1-K04SPEND4-TASK.md — per-1M cost-math fix on WT\OC-K04 (int 3c3277a base), single writer
KANAPKA K04SPEND4
GOAL (one line): divide charge-path cost by 1_000_000 (MODEL_KB prices are per-1M) + live hi with tiny nonzero spend, WT\OC-K04 only.
SPEC: DIRECTOR\TASK_PACKAGES\K04SPEND4\BRIEF_D.md (F1 /1e6 manager.py + run_store.py, 3 test expectations derived from MODEL_KB; F2 stub_scan 0; F3 live RAW tokens>0 + spent>0 + same-project ledger).
FILES YOU OWN (write ONLY these; inputs untouched):
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\src\agent_si\runtime\manager.py
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\src\agent_si\telemetry\run_store.py
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\tests\test_k04mr07b_spend_served.py
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\tests\test_k04bud1_budget_charge.py
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\tests\test_k04bind3_multi_provider.py
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\tests\test_k04spend01_live_shape_served.py
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\tests\test_k04spend3_persist_restart.py (new)
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\_task\K04SPEND4\CODER_RETURN.md (new) (your return only)
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\_task\K04SPEND4\*.md (lane paperwork: MANAGER/AUDIT returns, HD request)
- D:\AI_PROJECTS\AGENT_SI_BUILD\WT\OC-K04\_task\K04SPEND3V\* (prior verify lane of same fix chain, finished; defect source D-K04SPEND3V-01, evidence retained)
DONE MEANS (observable): served suites green; live spent tiny-but->0 same-project; stub_scan clean; CODER_RETURN.md written.
FORBIDDEN: other WTs, APP, queue writes; pushes; network except gateway live run; keys; installs; weakening tests to fit code; invented prices.
