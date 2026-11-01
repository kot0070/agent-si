# Agent SI — K10 release notes (lane B paper)

License metadata: MIT Copyright (c) 2026 Ivan Soprun. The full license text
ships as `LICENSE` at the checkout root and is shown by the installer
About screen (installer wiring is lane A, not this paper lane).

## What this paper bundle contains

- `LICENSE` — MIT license text, unchanged.
- `docs/third_party_notices/NOTICES.md` — aggregated third-party notices,
  enumerated read-only from the workspace dependency manifests. Five
  third-party runtime components are enumerated from this checkout's
  manifests (all MIT-licensed); the `licenses/` folder carries the project's
  own MIT text until per-component license texts are vendored.
- `docs/third_party_notices/release_report.json` — release report dataset.
  Paper-lane stand-in generated from stored records only (see `metrics`
  sources inside the file) until the K13 `ReportDatasetBuilder` lands; it
  must then be replaced by builder output, not edited by hand.

## Scope

Lane B paper only: licence, notices, release notes, release report export.
Installer packaging and About-screen wiring (lane A) and the acceptance drive
with the evidence table (lane C) are separate lanes and are not part of this
bundle.

## Sources

Frozen interface records: `RECORDS/day0/K13_MANIFEST.md`,
`RECORDS/day1/K02_INTERFACE.md`, `RECORDS/day1/K04_INTERFACE.md`.
All counts in the report dataset come from stored records and workspace
enumeration; no metric was estimated or generated.

## Known limitations

- The report dataset is a paper-lane stand-in; no execution telemetry store
  exists in this worktree yet, so run-level metrics are zero with stated
  sources, not measurements.
- No acceptance drive has been run on a packaged build yet (lane C).
- Installer metadata and About-screen wiring are pending (lane A).
