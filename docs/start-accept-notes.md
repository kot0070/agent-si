# Start/accept notes

Startup notes: what a clean start guarantees — idempotent settings/keys migration, identical green demo on restart, AGENT_SI_DATA_DIR wins, frontend installs offline from tarballs.

## Startup idempotence

Repeat startup is idempotent: settings plus keys migrate once with originals kept, and a destination file that already exists is never overwritten.

A second start over the same data dir reports `skipped-present` for
every file and changes nothing on disk.

## Restart

Restart from a clean state repeats the working startup with an identical result: the demo drive returns the same green payload on every fresh start.

To restart: stop the app, start again with an empty data dir, and
expect the same green demo payload as the previous run.

## Data-dir start path

The product start path supplies the data dir from the consumer-layer
env read AGENT_SI_DATA_DIR, never from harness settings; a blank
value fails loud, and an unset value yields no dir. A harness-sourced
dir that differs from the env dir is rejected.

## Frontend offline install

The frontend installs offline from cached tarballs only, never from
a registry at install time. Install from the checked-in
`frontend/package-lock.json` against the pre-fetched tarball cache;
the declared @types set (`@types/react`, `@types/react-dom`) stays
intact.

## Fixture runs

The recorded fixture suite runs with no cache provider:

`pytest tests/test_k10ph2d_served.py -q -p no:cacheprovider`
