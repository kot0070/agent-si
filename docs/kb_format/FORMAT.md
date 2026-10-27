# KB directory format (K09-B)

A knowledge base (KB) is a directory with three parts: a manifest, a purpose
declaration, and section files. `tools/kb_validator/iface.py`
(`validate_kb_dir`) accepts a directory exactly when all three are present,
checked in this order:

1. `manifest.json` must exist at the top level and parse as a JSON dict
   (an object, not a list or scalar). Otherwise `KB_MANIFEST_MISSING`.
2. At least one section file must exist: `sections/*.md`, or — via the
   documented flat-md adapter below — a top-level `*.md` file.
   Only `.md` files count, so `manifest.json` and `purpose.txt` never
   qualify as sections. Otherwise `KB_SECTIONS_MISSING`.
3. A purpose declaration must exist: a `purpose.txt` file, or a non-empty
   `"purpose"` string inside `manifest.json`. Otherwise
   `KB_PURPOSE_MISSING`.

## manifest.json

A JSON object. Conventional keys (see `templates/manifest.json`):

- `kb_id`: directory identity, mirrors the folder name.
- `purpose`: one or two sentences saying what this KB is for. This key
  alone satisfies the purpose declaration, even without `purpose.txt`.
- `sections`: list of section ids, matching the `.md` file stems.

## purpose declaration

Either a `purpose.txt` file at the top level, or a non-empty `"purpose"`
string in `manifest.json`. Providing both is fine; the well-formed example
in `tests/fixtures/k09b/good` does both.

## sections

One Markdown file per section, normally under `sections/`:

```text
<kb>/
  manifest.json
  purpose.txt
  sections/
    intro.md
    setup.md
```

The section id is the file stem (`intro.md` → `intro`).

## The ONE adapter: flat-md layout

A KB dir with no `sections/` subfolder is still accepted when `.md` files
live directly at the top level of the KB dir (`manifest.json` plus the
purpose declaration are still required at top level). This is the only
supported alternate layout. Section ids are the same file stems.

## Error codes

| Code | Meaning |
|---|---|
| `KB_MANIFEST_MISSING` | Not a dir, or `manifest.json` missing, unparseable, or not a JSON dict |
| `KB_SECTIONS_MISSING` | No `sections/*.md` and no flat top-level `*.md` |
| `KB_PURPOSE_MISSING` | No `purpose.txt` and no non-empty manifest `"purpose"` string |

A result is `KbValidationResult(ok, kb_dir, error_code)` with
`error_code=None` on success; the input `kb_dir` is echoed back.
