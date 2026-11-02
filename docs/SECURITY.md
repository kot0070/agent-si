# Security — Agent SI

## Key handling

- Provider keys live only in the Windows Credential Manager under the app namespace. Each entry is the app prefix plus the provider reference, with an optional label suffix.
- The app uses standard system calls to write, read, list names, and delete entries. Operations are time-bounded and never hang the interface.
- The key value is never echoed back, never logged, and never stored in settings files, browser storage, chat history, telemetry, or audit records. Only the entry name is ever shown.
- The frontend holds references only. The reference carries no key material. Saving clears the typed value from memory once the server answers.
- Saving or connecting without the session token is refused. A save that times out reports a timeout and keeps the old state.
- Disconnect deletes the stored entry. A leftover-entry finder lists names only so stray entries can be removed.

## Redaction

- Submissions are scanned for secret shapes (long token strings, key markers, password assignments) and for private paths (home folders, key files). Matches are blocked or masked before storage.
- Stored chat keeps only the project, the two texts, and the time. Extra fields are dropped. Secret-shaped text is replaced before writing.
- Logs replace bearer tokens, private-key blocks, and secret assignments with fixed markers. The redacted text is what stays in the file.
- Provider check outputs replace live stored values with a fixed marker before display.
- Telemetry redacts every known raw secret before an event is stored or exported. An event that still carries a raw secret is refused and never written.
- Tool output that prints environment values renders secret-looking values as references only.

## Permissions

- Install, network, and command steps go through an explicit permission ladder with three outcomes: allow, ask, or deny. Failures deny by default with a plain error code.
- Asks appear as clear buttons (allow once, allow for this project, deny). The decision is recorded per project. Install permission is asked once and then remembered.
- The folder picker calls a loopback endpoint guarded by the session check. The user picks, cancels, or (where no native window exists) sees no picker control at all.
- The desktop service listens on loopback only. Remote hosts cannot reach it.
- Local model and device steps stay on the machine. Docker and shell steps pass the same permission ladder and a loopback-host check.
- A check command runs with the user's rights: it can read and change the user's files, so run only checks you trust.

## What leaves the machine

- Only the provider call leaves the machine: the model request to the selected provider endpoint, using the key read from the OS store at call time. Nothing else carries key material.
- Hosted providers are reached at their public endpoints. Local providers stay on the loopback address and never leave the machine.
- The product notice states that a contributor-tier hosted option may use prompts and completions to train future models. Local use avoids this by staying on the machine.

## What to check before sharing

- Share the run, the decision record, and the audit verdict. They carry no key material.
- Do not copy the credential store, the raw log tail, or the browser storage dump. Export flows refuse secret-bearing runs without explicit approval.
