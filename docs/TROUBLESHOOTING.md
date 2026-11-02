# Troubleshooting — Agent SI

Each entry is a message the app actually shows. Follow the fix next to it.

## Providers and keys

- `Save timed out.` The key save took too long. Try again. If it repeats, restart the app and save once more.
- `This key does not match the expected format.` Check for extra spaces or a truncated paste, then re-enter the full key.
- `Refused: preset mismatch.` The key does not belong to the selected provider row. Pick the matching provider and save again.
- `Refused: no model for preset.` The provider row has no model bound. Bind a model first, then connect.
- `Save failed.` / `Connect failed.` / `Connect failed: <detail>` The provider refused the connection. Check the key, the network, and the provider status, then retry.
- `Connected <name>. Reference saved.` Success. The key is stored and only the reference is kept.
- `Refused: secret <name> is not bound to provider <name>.` Nothing was removed. Refresh the list and disconnect the correct row.
- `Could not list entries.` / `Delete failed.` The OS store did not answer. Restart the app and try once more.
- `Save failed for chat model.` The chat-model choice was not saved. Reopen Settings -> Models and save again.
- `The credential entry is missing.` The stored entry is gone. Connect the provider again.
- `Saving the key timed out.` Same as save timeout above. Retry once.

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

## Folders and permissions

- The Choose folder control hides itself where no native dialog exists. Type the folder path by hand and use Create.
- `The install permission was not granted.` Approve the one-time permission prompt (allow once or allow for this project), then retry.

## Clean start

- If the window cannot open and the message names the missing WebView2 runtime, install it from the link in the message and start the app again.
- If a previous data folder is reused, the app reports `skipped-present` for files that already exist and changes nothing. For a truly clean start, stop the app, use an empty data folder, and start again.
