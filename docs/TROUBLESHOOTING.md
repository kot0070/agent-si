# Troubleshooting — Agent SI

Each entry is a message the app actually shows. Follow the fix next to it.

## Providers and keys

- `Connect failed: Save timed out after 8000 ms.` The local reference write took too long. Try again. If it repeats, restart the app and save once more.
- `Connect failed: Save failed.` The local reference write failed. Restart the app and save once more.
- `Connect failed: KEY_SAVE_TIMEOUT (status 504).` The server key save timed out. Retry once. (Error panels elsewhere word the same condition as `Saving the key timed out.`.)
- `Connect failed: {code} (status {status}).` The provider refused the connection. Check the key, the network, and the provider status, then retry.
- `The provider refused this key. Paste the full key again.` The key is wrong or truncated. Nothing was stored — paste the full key, press Check, then Save.
- `Could not reach the provider.` The provider did not answer the key check. Check the network and the provider status, then press Check again.
- `Key checked. Save to connect.` The Check step passed, not an error: Save is now enabled — press it to connect.
- `This key does not match the expected format.` A pre-save warning only; Save still works. Check for extra spaces or a truncated paste, then save.
- `Refused: preset mismatch for {id}.` The dialog's provider row changed while it was open. Close it and open Connect on the matching provider again.
- `Refused: no model for preset {id}.` The provider row has no model to connect with. Pick a row with a model and connect again.
- `Connected {label}. Reference saved.` Success. The key is stored and only the reference is kept.
- `Refused: secret {secret} is not bound to provider {provider}.` Nothing was removed. Refresh the list and disconnect the correct row.
- `Could not list entries.` / `Delete failed.` The OS store did not answer. Restart the app and try once more.
- `Save failed for chat model.` The chat-model choice was not saved. Reopen Settings -> Models and save again.
- `The credential entry is missing.` The stored entry is gone. Connect the provider again.
- `Saving the key timed out.` Same server key-save timeout as above, worded by an error panel. Retry once.

## Tasks, routing, budget

- `The required context is missing.` The request arrived without its project or task context. Reload the project and retry.
- `Something went wrong. Try again.` Generic fallback. Retry; if it repeats, restart and report the step. The data-dir log folder (`<data>/logs/agent-si.log`, rotating 5 MB x 3) records the run id plus a redacted traceback; Settings > Diagnostics shows the folder path and opens it.
- `Connect a provider.` No model is bound yet. Go to Settings -> Models and connect one.
- `Task scopes overlap.` Two tasks claim the same scope. Narrow one scope and create again.
- `The quality gate did not pass.` The checks refused the result. Open the run and the audits tab for the failing check.
- `The task hierarchy chain is invalid.` The plan chain is broken. Re-plan from the top task.
- `The budget limit has been reached.` / `Blocked: the budget is exhausted.` Spend hit the limit. Raise the cap or start a new project.
- `No eligible model found.` No connected model fits the role. Connect a fitting model or switch the role to Auto.
- `The provider has no recorded evidence.` The provider has no successful record yet. Run a small task first.
- `Connection lost. Reconnecting.` The stream dropped. Wait for reconnect; resend only if the status stays offline.
- `Choose a project to set the model hierarchy.` Open or create a project first.

## Code tests

- `has no python interpreter: install Python or set AGENT_SI_PYTHON to a python executable` (shown with the test id and folder). Install a real Python on PATH, or point `AGENT_SI_PYTHON` at one. On Windows, a `python` that only opens the Microsoft Store never counts (the `py` launcher is tried instead); worker runs word a missing tool as `could not start: {tool} is not installed`.

## Folders and permissions

- The Choose folder control hides itself where no native dialog exists. Type the folder path by hand and use Create.
- `Install permission denied for {command}.` The run wants to install packages. Answer Allow once or For this project to let it continue, or Deny to stop it.

## Clean start

- If the window cannot open and the message names the missing WebView2 runtime, install it from the link in the message and start the app again.
- If a previous data folder is reused, the app reports `skipped-present` for files that already exist and changes nothing. For a truly clean start, stop the app, use an empty data folder, and start again.
