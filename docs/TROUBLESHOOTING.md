# Troubleshooting — Agent SI

Each entry is a message the app actually shows. Follow the fix next to it.

## Running from source

- `ModuleNotFoundError: No module named 'uvicorn'`. `src/agent_si/sidecar.py` imports `uvicorn` when it
  starts, and `pyproject.toml` does not list it. Install it into the same environment:
  `.\.venv\Scripts\python.exe -m pip install uvicorn`.
- `Agent SI web UI is not staged: the web tree holds no index.html`. The sidecar serves
  `frontend/dist`, which the web build writes. Run `npm --prefix frontend install`, then
  `npm --prefix frontend run build`, and start the app again.
- The app answers on a loopback address but the window does not open: the WebView2 runtime is missing or
  the window could not start. The app opens the same address in your default browser and keeps serving;
  install WebView2 from the link in the notice to get the native window back.
- `agent-si` prints nothing and exits: that console script points at the app factory
  `agent_si.backend.app:create_app`, not at the window. Start the app with
  `python -m agent_si.sidecar`.

## Providers and keys

- `Save timed out after 8000 ms.` The local reference write took too long. Try again. If it repeats,
  restart the app and save once more.
- `The key was not saved: the store gave no answer.` The local reference write failed. Restart the app
  and save once more.
- `Connect failed: KEY_SAVE_TIMEOUT (status 504).` The server key save timed out. Retry once. (Error
  panels elsewhere word the same condition as `Saving the key timed out.`.)
- `Connect failed: {code} (status {status}).` The provider refused the connection. Check the key, the
  network, and the provider status, then retry.
- `Connect failed: {message}` / `Connect failed before the server answered.` The route sent a plain
  reason, or the request never reached it. Retry, then restart the app.
- `The provider refused this key. Paste the full key again.` The key is wrong or truncated. Nothing was
  stored — paste the full key, press Check, then Save.
- `The provider is slow or unreachable. Your key is saved. Press Connect again.` The check did not get
  an answer in time. Check the network and the provider status, then press Connect again.
- `Key checked. Save to connect.` The Check step passed, not an error: Save is now enabled — press it to
  connect.
- `Check the key first.` Save was pressed before Check. Press Check, then Save.
- `This key does not match the expected format.` A pre-save warning only; Save still works. Check for
  extra spaces or a truncated paste, then save.
- `Refused: preset mismatch for {id}.` The dialog's provider row changed while it was open. Close it and
  open Connect on the matching provider again.
- `Refused: no model for preset {id}.` The provider row has no model to connect with. Pick a row with a
  model and connect again.
- `This provider is already connected with different settings — disconnect it first, then connect again.`
  Disconnect that row in Settings -> Models, then connect with the new settings.
- `Connected {label}.` Success. The key is stored and only the reference is kept.
- `Refused: secret {secret} is not bound to provider {provider}.` Nothing was removed. Refresh the list
  and disconnect the correct row.
- `Could not list entries.` / `Delete failed.` The OS store did not answer. Restart the app and try once
  more.
- `Save failed for chat model.` The chat-model choice was not saved. Reopen Settings -> Models and save
  again.
- `The credential entry is missing.` The stored entry is gone. Connect the provider again.
- `Saving the key timed out.` Same server key-save timeout as above, worded by an error panel. Retry once.
- `Couldn't refresh the live list — keeping the last list.` The model refresh failed; the previous list
  stays. Press Refresh models again later.

## Local models (Ollama, Muse Glimmer)

- `Local server is not running. Start Ollama first, then Check again.` The app asked the loopback address
  and nothing answered. Start Ollama on this PC (it listens at `http://localhost:11434`), then press
  Check again. LM Studio uses `http://localhost:1234/v1`.
- `Local server answered: found {count} models. Save to connect.` Not an error: the server is up and the
  count is real. Press Save.
- The model is not in the Local models list after `ollama pull muse-glimmer:30b`: the list is read from
  the running server. Start Ollama first, then reopen Settings -> Local LLM (or press Check) so the list
  is fetched again.
- `Worker model not set: {reason}.` Use for agents could not pin the model on the worker role. Read the
  reason, reopen Settings -> Local LLM and press Use for agents again.
- `No capability data for {model}; it can still be used.` Not an error: the shipped knowledge base has no
  row for that local model. Routing falls back to the default fit.
- A 30B model needs about 18 GB of free disk. On 8 GB of video memory it runs split with the CPU and is
  slow; a smaller local model or a hosted key is the fast path.

## Watcher and automations

- A watcher rule card reads Evaluate off: turn the card on to evaluate. `No backend rule for this card;
  evaluation runs on the guard and tamper cards.` means that specific card has no backend yet — the guard
  and tamper cards do the work.
- Restart once, pause and stop wait for you: tick `I approve this one check` before they act.
- `Automations are stopped - turn the stop switch off first.` Nothing runs while Stop all automations or
  Stop automations for this project is on. Turn the switch off and try again.
- `No journal rows yet` / `No action yet`: the watcher has not acted since this start. That is not a
  failure.
- `Integrity mismatch` on the integrity check: a watched file changed outside the app. Read the alerts
  list before turning anything else on.

## Tasks, routing, budget

- `The required context is missing.` The request arrived without its project or task context. Reload the
  project and retry.
- `Something went wrong. Try again.` Generic fallback. Retry; if it repeats, restart and report the step.
  The data-dir log folder (`<data>/logs/agent-si.log`, rotating 5 MB x 3) records the run id plus a
  redacted traceback; Settings > Diagnostics shows the folder path and opens it with Open log folder.
- `Connect a provider first, then send your task again.` No model is bound yet. Go to Settings -> Models
  and connect one.
- `Task scopes overlap.` Two tasks claim the same scope. Narrow one scope and create again.
- `The quality gate did not pass.` The checks refused the result. Open the run and the audits tab for the
  failing check.
- `The task hierarchy chain is invalid.` The plan chain is broken. Re-plan from the top task.
- `The budget limit has been reached.` / `Blocked: the budget is exhausted.` Spend hit the limit. Raise the
  cap in Settings -> Project or start a new project.
- `No eligible model found.` No connected model fits the role. Connect a fitting model or switch the role
  to Automatic.
- `The provider has no recorded evidence.` The provider has no successful record yet. Run a small task
  first.
- `Connection lost. Reconnecting.` The stream dropped. Wait for reconnect; resend only if the status stays
  offline.
- `Choose a project to set the model hierarchy.` Open or create a project first.

## Test catalog

- `Loading test catalog…` stays on screen: the catalog read did not answer. Press Retry.
- `Retry` with an error line under it: the read failed. Retry once; if it repeats, reopen Settings -> Test
  catalog.
- `Activate failed.` The chosen catalog version was not activated. Nothing changed; pick the version again
  or stay on the active one shown at the top of the screen.

## Code tests

- `has no python interpreter: install Python or set AGENT_SI_PYTHON to a python executable` (shown with
  the test id and folder). Install a real Python on PATH, or point `AGENT_SI_PYTHON` at one. On Windows, a
  `python` that only opens the Microsoft Store never counts (the `py` launcher is tried instead); worker
  runs word a missing tool as `could not start: {tool} is not installed on this machine; ...`.

## Folders and permissions

- The Choose folder control hides itself where no native dialog exists. Type the folder path by hand and
  use Create.
- `The project folder is missing. Pick another folder in Projects, then send again.` The stored folder
  moved or was deleted. Pick the folder again in Projects.
- `This folder is already used by another project.` Pick a different folder, or open the project that
  already owns it.
- `Install permission denied for {command}`. The run wants to install packages. Answer Allow once or For
  this project to let it continue, or Deny to stop it (`Stopped: you denied {command}. Nothing was
  installed.`).

## Clean start

- If the window cannot open and the message names the missing WebView2 runtime, install it from the link in
  the message and start the app again.
- If a previous data folder is reused, the app reports `skipped-present` for files that already exist and
  changes nothing. For a truly clean start, stop the app, use an empty data folder (or point
  `AGENT_SI_DATA_DIR` at an empty one), and start again.
