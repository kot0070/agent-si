# Scene plan — ONE 3-minute 14-function cut (matches demo-script.md)

Scope (production note, not visitor text): owned file `SUBMISSION/K12/scene-plan.md`.
Status: claim evidence is tracked in `SUBMISSION/ANSWERS_DRAFT.md`.
Same ONE script as `demo-script.md`: same 14 scenes, same seconds, same play order.
Total 174s (<=180s). Every scene evidence is `PENDING-DRIVE`.

## Play order (seconds match demo-script.md exactly)

1. 0-15, F04 — one task given. Clicks: Tasks → «Create task», Chat → «Send».
   Voice-over: «Ставимо одне завдання: план, паралельні виконавці, перевірки й чесний висновок аудитора.»
2. 15-27, F01 — team builds it, code first. Clicks: Projects → «Runs»,
   explainer → «Code tests», «Local tests».
   Voice-over: «Перевірки йдуть від дешевого до дорогого: спочатку код, потім хмарний помічник, людина — в останню чергу.»
3. 27-39, F02 — fixed hierarchy. Clicks: Settings → «Role profile», mode → «Pinned».
   Voice-over: «Закріплюємо виконавця за кожним рівнем: видно, хто відповідає і яка модель записана.»
4. 39-51, F03 — AUTO hierarchy. Clicks: Settings → «Role profile», mode → «Automatic».
   Voice-over: «Вмикаємо автоматичний режим на кожному рівні: система бере найдешевший придатний варіант і записує чому.»
5. 51-63, F08 — provider connects by key. Clicks: Providers →
   «Search providers or models», connect dialog → «Save».
   Voice-over: «Підʼєднуємо постачальника лише ключем: жодних зайвих налаштувань.»
6. 63-80, F05 — control plus telemetry cards (P3-D1 beat). Clicks: Sidebar → «Agents live»,
   panel → «Live agents»; Diagnostics → Telemetry route `/diagnostics/telemetry`
   (`frontend/src/app/App.tsx:816`, testid `k07next2-telemetry`
   `frontend/src/k07next2/TelemetrySummary.tsx:163`).
   Voice-over: «Панель показує всю команду наживо: роль, модель, крок, витрати й токени. А картки телеметрії зводять виміряні підсумки: події, записи й витрати кожної моделі.»
7. 80-90, F06 — watcher. Clicks: Top bar → «Watcher».
   Voice-over: «Тихий спостерігач стежить за кожним кроком і записує все до журналу.»
8. 90-102, F07 — stop (P3-D3 closed: FXLAST disabled-when-idle; shoot with a LIVE run only).
   Clicks: Top bar → «Stop all».
   Voice-over: «Одна дія зупиняє все одразу, а зроблене й записи зберігаються.»
9. 102-115, F10 — safety benchmark. Clicks: Settings → «Local benchmark»,
   «Scan models» → «Run benchmark».
   Voice-over: «Вимірюємо локальні моделі до роботи: оцінки й рішення записуються.»
10. 115-132, F12 — money plus token saving (P3-D2 beat). Clicks: Project → «Cost» budget line,
    project view → «Tokens» tab (`frontend/src/app/App.tsx:77`, tab `project-menu-tokens`;
    served fact `tokens-spent` `frontend/src/projects/ProjectView.tsx:1150`, rows
    `tokens-row-{index}` `:1161` — per-role/per-model cells from live rows plus the
    analytics telemetry doc, never invented).
    Voice-over: «Бюджет під контролем: видно витрати, межу й ліміти кожного постачальника. А вкладка токенів показує, скільки взяв на себе код, а скільки — хмарний помічник.»
11. 132-142, F09 — model knowledge. Clicks: Settings → «Capability Database».
    Voice-over: «База знань про моделі: що кожна вміє, з доказами, і пропозиції оновлення.»
12. 142-152, F11 — attached knowledge. Clicks: view → «Knowledge bases».
    Voice-over: «Долучаємо базу знань до роботи: пропозиція проходить перевірку перед увімкненням.»
13. 152-162, F13 — install permission. Clicks: Project → «I accept the risk».
    Voice-over: «Дозвіл на встановлення питаємо один раз — і більше не турбуємо.»
14. 162-174, F14 — clean install. Clicks: First run → «Welcome to Agent SI»,
    wizard → «Next».
    Voice-over: «Нове встановлення починається з чистого аркуша: жодних слідів попередньої роботи.»

## Cut notes

- One continuous voice-over, one beat per scene, app page only; total 174s (cap 175s),
  newcomer view. Arithmetic (durations in play order):
  15 + 12 + 12 + 12 + 12 + 17 + 10 + 12 + 13 + 17 + 10 + 10 + 10 + 12 = 174;
  174 < 175. The two new beats (+4s F05 telemetry cards, +4s F12 token-saving tab)
  are paid by -2s each on F06, F09, F11, F13 (12s -> 10s); all other steps keep
  their seconds. 14-step shape kept: demo_video.py load_storyboard requires
  exactly 14 steps, so telemetry and saving land as beats inside F05/F12, not
  as new step ids.
- New voice takes needed: F05 (extended line with the telemetry-cards beat) and
  F12 (extended line with the token-saving beat). F06/F09/F11/F13 clips
  (4.77s/5.09s/4.07s/3.82s per VIDEO_MISSING.md) still fit their new 10s windows:
  no new take, verify at mux. All other clips untouched. Note: current clips are
  ENGLISH V2 while demo-script.md lines are Ukrainian (VIDEO_MISSING.md) — record
  the two new takes in the shoot language per the owner call.
- Hierarchy across providers with AUTO at every level (scenes 3-4), Watcher journal
  (scene 7), telemetry cards on the REAL route `/diagnostics/telemetry`
  (`k07next2-telemetry`, scene 6 second beat), Stop all with a LIVE run only
  (scene 8, FXLAST disabled-when-idle), measured token saving code-vs-AI from the
  served Tokens tab rows (`tokens-spent`, `tokens-row-{index}`, scene 10 second
  beat; figures are the live served values at shoot time, never invented).
- Visuals stay proportional to measured figures; figures switchable later.
- Consistency: scene order, seconds, clicks, on-screen, proves, voice-over lines and
  `PENDING-DRIVE` evidence are identical to `demo-script.md`.
