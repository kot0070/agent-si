# Release files: hashes and smoke checks

Release: https://github.com/kot0070/agent-si/releases/tag/v0.1.0
Built from commit 57295e863393c8c8f9577fdc5386cdfe5e0c6819 (branch pkg/PLANB); built_from_commit in HASH.json is the same.

Files and SHA-256 (same values as the SHA256SUMS.txt index published with the release):
- AgentSI-setup-0.1.0.exe: 98203636 bytes, SHA-256 aec6d70c24c5ab52618fd701e2fcf2e37cca0529a6e82193d146578adf5b9c32
- AgentSI-portable-0.1.0.zip: 96913003 bytes, SHA-256 bee806586865fbddd1f5934b06f37b0b4bbf05e8a97362ba941b56f023c5a25d
- SHA256SUMS.txt (both, format <sha256>  <filename>; same values as the build's own index)

Smoke checks before publishing (both passed):
- Portable: hash matched its SHA256SUMS line, zip unblocked and unpacked into an empty folder, AgentSI.exe started with a fresh data folder; GET / = 200 and GET /firstrun = 200; the test's own process tree was stopped.
- Installer: hash matched, silent install for the current user exited 0 (Start-menu folder, desktop shortcut and uninstall entry created, as the README says); the installed app answered 200 on / and /firstrun; the silent uninstall exited 0 and removed the folder, shortcuts and registry key. The interactive wizard and the "delete data?" prompt were not driven (silent only).

Zip scan (67 entries, no data folder): no keys, no .env, no database or key files, no secrets or credentials files, no logs, no caches, no test folders; the text files and AgentSI.exe contain no local paths, no key patterns (sk-, AKIA, PRIVATE KEY). Only benign hits: the word "Director" (a product role) and licence text.
