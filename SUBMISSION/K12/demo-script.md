# Demo script — ONE 3-minute 14-function cut (app page only)

Scope (production note, not visitor text): owned file `SUBMISSION/K12/demo-script.md`.
Status: the script stays the play record; claim evidence is tracked in
`SUBMISSION/ANSWERS_DRAFT.md`. Fourteen functions in one cut, all NOT
STARTED at write time, so every evidence cell is `PENDING-DRIVE`; story
arc F04 -> F01, F02, F03, F08 -> F05, F06, F07 ->
F10 -> F12 -> F09, F11 -> F13, F14. Total 174s (<=180s). Click labels are the
default-locale strings as rendered, each
verified by a `t("...")` use in `frontend/src`. Voice-over lines are Ukrainian and number-free.

| seconds (start-end) | function # | clicks (page + control label) | on-screen | proves | voice-over | evidence |
|---|---|---|---|---|---|---|
| 0-15 | F04 | Tasks → «Create task» (`frontend/src/tasks/TaskComposer.tsx:225`); Chat → «Send» (`frontend/src/chat/index.tsx:390`) | task plan, parallel managers, executed checks, fresh-auditor verdict | one task becomes a verified result through the full chain | «Ставимо одне завдання: план, паралельні виконавці, перевірки й чесний висновок аудитора.» | PENDING-DRIVE |
| 15-27 | F01 | Projects → «Runs» (`frontend/src/k07next2/RunsLedgerFresh.tsx:27`); explainer → «Code tests», «Local tests» (`frontend/src/app/HowItWorks.tsx:10-13`) | run ledger ordered code-first | catalog runs local code first, AI next, human last | «Перевірки йдуть від дешевого до дорогого: спочатку код, потім хмарний помічник, людина — в останню чергу.» | PENDING-DRIVE |
| 27-39 | F02 | Settings → «Role profile» (`frontend/src/settings/ContractDefaultsBar.tsx:65`); mode → «Pinned» (`frontend/src/settings/ContractDefaultsBar.tsx:23`) | every level pinned, each level's model recorded | fixed hierarchy with recorded models | «Закріплюємо виконавця за кожним рівнем: видно, хто відповідає і яка модель записана.» | PENDING-DRIVE |
| 39-51 | F03 | Settings → «Role profile» (`frontend/src/settings/ContractDefaultsBar.tsx:65`); mode → «Automatic» (`frontend/src/settings/ContractDefaultsBar.tsx:28`) | AUTO at every level plus the recorded reason | cheapest fitting connected model, why recorded | «Вмикаємо автоматичний режим на кожному рівні: система бере найдешевший придатний варіант і записує чому.» | PENDING-DRIVE |
| 51-63 | F08 | Providers → «Search providers or models» (`frontend/src/settings/ProvidersPage/ProvidersPage.tsx:184`); connect dialog → «Save» (`frontend/src/settings/ProvidersPage/ConnectDialog.tsx:167`) | provider connected, key stored | catalog connects with the key only | «Підʼєднуємо постачальника лише ключем: жодних зайвих налаштувань.» | PENDING-DRIVE |
| 63-76 | F05 | Sidebar → «Agents live» (`frontend/src/shell/Sidebar.tsx:24`); panel → «Live agents» (`frontend/src/k07next4/TurnTripleBoard.tsx:25`) | role, model, step, cost, tokens per running agent | compact panel controls the whole team | «Панель показує всю команду наживо: роль, модель, крок, витрати й токени.» | PENDING-DRIVE |
| 76-88 | F06 | Top bar → «Watcher» (`frontend/src/shell/TopBar.tsx:132`) | independent watcher reacts; journal gains an entry | watcher observes, journal records | «Тихий спостерігач стежить за кожним кроком і записує все до журналу.» | PENDING-DRIVE |
| 88-100 | F07 | Top bar → «Stop all» (`frontend/src/shell/TopBar.tsx:140`) | all runs halt at once; partial outputs and records stay | one action stops everything | «Одна дія зупиняє все одразу, а зроблене й записи зберігаються.» | PENDING-DRIVE |
| 100-113 | F10 | Settings → «Local benchmark» (`frontend/src/k07next5/BenchSettingsTab.tsx:33`); «Scan models» → «Run benchmark» (`frontend/src/settings/LocalBenchTab.tsx:344,404`) | per-model scores plus the decision record | local models measured before use | «Вимірюємо локальні моделі до роботи: оцінки й рішення записуються.» | PENDING-DRIVE |
| 113-126 | F12 | Project → «Cost» budget line (`frontend/src/settings/projectLimits.tsx:155`); project view → «Tokens» (`frontend/src/projects/ProjectView.tsx:673`) | spent against hard limit, per-provider caps | budget and caps enforced | «Бюджет під контролем: видно витрати, межу й ліміти кожного постачальника.» | PENDING-DRIVE |
| 126-138 | F09 | Settings → «Capability Database» (`frontend/src/settings/index.ts:27`) | per-model evidenced capabilities and the refresh proposal | model KB with Update | «База знань про моделі: що кожна вміє, з доказами, і пропозиції оновлення.» | PENDING-DRIVE |
| 138-150 | F11 | View → «Knowledge bases» (`frontend/src/k07next2/KbRefreshProposal.tsx:25`) | attached-KB proposal and its validation state | knowledge-base attachment | «Долучаємо базу знань до роботи: пропозиція проходить перевірку перед увімкненням.» | PENDING-DRIVE |
| 150-162 | F13 | Project → «I accept the risk» (`frontend/src/settings/index.ts:338` renders `settings.risk.label`) | one-time permission prompt, then never again | install permission asked once | «Дозвіл на встановлення питаємо один раз — і більше не турбуємо.» | PENDING-DRIVE |
| 162-174 | F14 | First run → «Welcome to Agent SI» (`frontend/src/k07next/NewcomerGuide.tsx:25`); wizard → «Next» (`frontend/src/app/firstrun/FirstRunFlow.tsx:106`) | zero projects, runs, keys and test rows | fresh install starts clean | «Нове встановлення починається з чистого аркуша: жодних слідів попередньої роботи.» | PENDING-DRIVE |
