# Agent SI packaging notes — portable build 0.1.0

What the portable zip holds ([../dist/AgentSI-portable-0.1.0.zip](../dist/AgentSI-portable-0.1.0.zip)): the ready-to-run app — `AgentSI.exe` (sidecar plus app copy), the web UI tree, migrations, locale files, kb-data, watcher, LICENSE, the third-party notices file with its licence texts, `MANIFEST.json`, `HASH.json` with `HASH.json.sha256`, `SMOKE.json`, `README.txt`, `SHA256SUMS.txt`, and the Start-AgentSI launchers.

How the hash is checked: verify both SHA256 values (the exe and the manifest hash in the README Portable build section) against the `SHA256SUMS.txt` shipped in the bundle — PowerShell: `Get-FileHash -Algorithm SHA256` — then re-verify from the checkout with [installer_manifest/gen_smoke.py](installer_manifest/gen_smoke.py) (`--root .`). Hashes are re-stamped on every release — never trust hashes older than int HEAD.

The exe is unsigned: expect one Windows SmartScreen warning. First start on an empty profile asserts an empty store with a native window and no console.
