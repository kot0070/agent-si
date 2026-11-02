# Release notes — Agent SI 0.1.0 (RC4 dry-run values)

Prefer the installer first: `AgentSI-setup-0.1.0.exe` installs this same
folder per user (see README "Download and verify"). This package is the
portable second option: an unsigned portable folder build for Windows —
unzip the folder, run AgentSI.exe inside it, never copy the exe out.

Agent SI is a desktop app for running a small team of AI agents:
one task becomes a plan, the plan splits into parallel work, checks
run, and a fresh auditor gives an honest verdict.

This build is not code-signed - verify the SHA256 below.

## Verify

PowerShell, from the folder holding the zip:

```powershell
Get-FileHash -LiteralPath .\AgentSI-portable-RC4-0.1.0.zip -Algorithm SHA256
```

Unzip, open the `AgentSI` folder inside it, then (from the folder holding the zip):

```powershell
Get-FileHash -LiteralPath .\AgentSI\AgentSI.exe -Algorithm SHA256
```

Expected values (measured at pack time from the exact files shipped):

- portable zip SHA256: 79eb0a9f7007fe88f12019c4bca0d52142d956dc2f9f75a8ca1d33239e410090
- AgentSI.exe SHA256: 30a109dac4adc14cd2c709326211d3704eac11b69103a96231e7df8f0eb268ca
- MANIFEST canonical SHA256 (HASH.json): 73f947a738d82edfdea9785a9088d18b379549729f25ff60285b795fffdbdda3

Run AgentSI.exe inside it (double-click it, or `Start-AgentSI.cmd`
beside it). Never copy the exe out of its folder: it needs its support
files beside it. The MANIFEST value is the hash of the canonical manifest
bytes, not of the exe; the exe value above is the one to compare against
AgentSI\AgentSI.exe. The pack step regenerates all three values from the
shipped files; a release whose values differ from a fresh measurement
must not ship. Expect one Windows SmartScreen warning ("Windows protected
your PC", publisher Unknown): the exe is unsigned. Click More info, then
Run anyway — only after the SHA256 values above match. If the zip was downloaded, unblock it before unzipping
(right-click the zip, Properties, Unblock).

## Known limits (RC4)

- 12 open FAIL rows plus 2 SKIPPED-OLLAMA-BUSY rows out of 51
  (disconnect click blocked, AUTO label absent, team panel absent,
  install run not terminal, routes splits, outage journal,
  two-provider match, clean-profile disconnect; local benchmark and
  local-failure rows skipped, Ollama untouched).
- Install permission asked-once: store record exists, live behaviour
  unproven (STORE-ONLY).
- Local-AI benchmark: no evidence (Ollama legs never ran).
- The bundle ships test and hygiene leftovers that the next build
  must drop: locale/__tests__ test files, 23 __pycache__ .pyc files.
- One shipped comment names an internal location
  (kb-data/model_kb/loader.py line 327); the comment text must be
  rewritten before release.
- Licence: MIT, Copyright (c) 2026 Ivan Soprun. Third-party notices
  ride in docs/third_party_notices.
