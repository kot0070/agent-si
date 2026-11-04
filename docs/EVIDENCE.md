# Development screenshots: evidence

Each image is a cropped and resized copy (max 1600 px wide, JPG) of a photo taken during development. Originals are not in the repo.

- `screenshots/firstrun-welcome.jpg`: First-run "Welcome to Agent SI" page with four provider cards (Meta, OpenAI, Anthropic, Ollama); nothing connected yet. during development, November 2026. The app can use other providers; the hackathon demo calls only Meta models.
- `screenshots/firstrun-meta-connected.jpg`: Same welcome page after Meta is connected; the Meta card says "Connected Meta." during development, November 2026.
- `screenshots/providers-page.jpg`: Providers page: Meta shows "0 enabled"; the OpenAI section lists gpt-4o-mini and gpt-4o with status "not known". during development, November 2026. The app can use other providers; the hackathon demo calls only Meta models.
- `screenshots/meta-model-list.jpg`: Meta model list on the Providers page; meta/muse-spark-1.3-contributor (Standard) is ticked and the Meta card shows "1 enabled". during development, November 2026.
- `screenshots/team-pool-picker.jpg`: Team role picker in Ukrainian with the "Model pool" option selected; the dropdown lists Meta models and Ollama entries. during development, November 2026. The app can use other providers; the hackathon demo calls only Meta models.
- `screenshots/knowledge-base-status.jpg`: Knowledge base status panel: version 2 applied, provider meta, model meta/muse-spark-1.3-contributor, and the status line KB_VALIDATION_FAILED. during development, November 2026.

## First passes on Muse Spark (photos of a screen)

These five images are photos of a computer screen taken with a phone, not screenshots. They are cropped and resized (JPG, max 1600 px). Where a line showed the working folder on the PC, it is covered with a black box. They show real runs through the Meta Model API with meta/muse-spark-1.3-contributor; the dates printed in the app are shown where the photo has them.

- `screenshots/muse-spark-first-pass-1.jpg`: Photo of a screen, November 2, 2026. Chat task "Create a file hello.txt with the text hello". Team: director, manager, worker, auditor on meta/muse-spark-1.3-contributor; plan of 1 part; "Auditor for p1: PASS". The photo was taken while the run went on: the last line reads "Part p1: checks red, attempt 2". The auditor record id and the working folder are covered.
- `screenshots/muse-spark-first-pass-2.jpg`: Photo of a screen, November 2, 2026. The same kind of run, finished: "Part p1: PASS (checks green, auditor PASS)", "Total: 784 input + 4128 output = 4912 tokens; cost: UNKNOWN", "run success: all 1 parts PASS". The side panel still reads "Tokens 0" and "Unknown" at that time. The working folder is covered.
- `screenshots/muse-spark-first-pass-3.jpg`: Photo of a screen, November 2, 2026. The same finished run with the whole chat in view and the status line "Auto | Cloud | Ready". The working folder is covered.
- `screenshots/muse-spark-first-pass-4.jpg`: Photo of a screen. A later run in the chat with Auto routing: "Total: 617 input + 4525 output = 5142 tokens; cost: UNKNOWN", "run success: all 1 parts PASS". Below it a second task, "Install dependencies with npm install", has started and the status line reads "Working". The app shows the times 07:34 AM and 07:37 AM. The working folders are covered.
- `screenshots/muse-spark-tokens-tab.jpg`: Photo of a screen. The Tokens tab: tokens per role and model, all on muse-spark-1.3-contributor. The role rows read "Unknown" (the app did not know those counts yet); "Other calls" show 59,167 tokens in 18 calls. The page also says "not known yet" for the total, so the numbers are what the app knew, not an invention.
