# Release notes — Agent SI 0.1.0

Agent SI 0.1.0, built for the Meta Global AI Developer Hackathon.
Release page: https://github.com/kot0070/agent-si/releases/tag/v0.1.0

Agent SI is a desktop app for running a small team of AI agents:
one task becomes a plan, the plan splits into parallel work, checks
run, and a fresh auditor gives an honest verdict.

## Download one

- `AgentSI-setup-0.1.0.exe`: installer for Windows 10 or 11, 64-bit, per user. Prefer this one.
- `AgentSI-portable-0.1.0.zip`: unzip, open the `AgentSI` folder and run AgentSI.exe inside it. Never copy the exe out of its folder: it needs its support files beside it.
- `SHA256SUMS.txt`: the hashes of both files.

To run a team you need a model: a key for the Meta Model API, or Muse Glimmer locally through Ollama (`ollama pull muse-glimmer:30b`, about 18 GB; slow on 8 GB of video memory). The app opens and shows its screens without one.

## Verify

This build is not code-signed, so check the hash before you run it. PowerShell, from the folder holding the download:

```powershell
Get-FileHash -LiteralPath .\AgentSI-setup-0.1.0.exe -Algorithm SHA256
Get-FileHash -LiteralPath .\AgentSI-portable-0.1.0.zip -Algorithm SHA256
```

Expected values, the same as in `SHA256SUMS.txt`:

- `AgentSI-setup-0.1.0.exe`: aec6d70c24c5ab52618fd701e2fcf2e37cca0529a6e82193d146578adf5b9c32
- `AgentSI-portable-0.1.0.zip`: bee806586865fbddd1f5934b06f37b0b4bbf05e8a97362ba941b56f023c5a25d

Both were built from commit `57295e8`. Sizes and smoke checks: [release-hashes.md](../evidence/release-hashes.md).

Expect one Windows SmartScreen warning ("Windows protected your PC", publisher Unknown): the build is unsigned. Click More info, then Run anyway, only after the value matches. If the zip was downloaded, unblock it before unzipping (right-click the zip, Properties, Unblock).

## Known limits

The current list is in [Known issues](../KNOWN_ISSUES.md).

Licence: MIT, Copyright (c) 2026 Ivan Soprun. Third-party notices are in `docs/third_party_notices`.
