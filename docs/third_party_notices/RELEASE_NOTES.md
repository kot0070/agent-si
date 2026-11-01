# Agent SI 0.1.0 — release notes

Licence metadata: MIT Copyright (c) 2026 Ivan Soprun. The full licence text
ships as [LICENSE](../../LICENSE) at the checkout root and is shown by the
About screen, which also lists the third-party titles; installer signing is
out of scope for unsigned 0.1.0.

## What this bundle contains

- `LICENSE` — MIT licence text, unchanged.
- [NOTICES.md](NOTICES.md) — aggregated third-party notices,
  enumerated read-only from the workspace dependency manifests. Notices cover
  the 5 manifest components plus the 5 frozen sidecar components; vendored
  texts live in [licenses/](licenses/) (proxy_tools: MIT per installed
  METADATA, no separate file).
- [release_report.json](release_report.json) — release report dataset.
  Generated from stored records only (see `metrics` sources inside the file).

## Scope

Scope: licence + notices + report dataset; installer signing and the
packaged-build acceptance drive are tracked separately in
[../release/RELEASE_CHECKLIST.md](../release/RELEASE_CHECKLIST.md).

## Sources

Frozen records: [RECORDS/day0/K13_MANIFEST.md](../../RECORDS/day0/K13_MANIFEST.md)
and the frozen interface stubs under [iface/](../../iface/): `iface/frozen_k04/K04_INTERFACE_STUB.py`,
`iface/frozen_k04/K04_INTERFACE_STUB_v2_MAP13.py`,
`iface/frozen_k04/K04_INTERFACE_STUB_v3_ADD412.py`,
`iface/frozen_manifest/interface_stub.py`, `iface/frozen_manifest/manifest.py`,
`iface/frozen_manifest/K13_MANIFEST.md`.
All counts in the report dataset come from stored records and workspace
enumeration; no metric was estimated or generated. Every cited file ships
with the bundle.

## Known limitations

Non-LIVE rows in [../release/RELEASE_CHECKLIST.md](../release/RELEASE_CHECKLIST.md)
stay PENDING-REDRIVE and carry the same limitation lines here; no claim ships
as proven without its DEFECTS line. Anything not yet measured is marked
PENDING-REDRIVE, never shipped as proven.
