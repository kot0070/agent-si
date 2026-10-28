# KB builder guide (K09-B)

How to build a KB directory that passes validation. The full shape contract
is in [FORMAT.md](FORMAT.md); start from the templates in
[templates/](templates/).

## Steps

1. Copy [templates/manifest.json](templates/manifest.json) to
   `<your-kb>/manifest.json` and fill in `kb_id`, `purpose`, `sections`.
2. Copy [templates/section.md](templates/section.md) to one file per
   section: `<your-kb>/sections/<id>.md` for each id in `sections`
   (or place `<id>.md` directly at the top level for the flat-md layout).
3. Declare the purpose: keep the `purpose` string in `manifest.json`,
   and/or add `<your-kb>/purpose.txt`.
4. Validate with the CLI (repo-relative commands, run from the repo root):

```text
D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe tools\kb_validator\validate_kb.py <your-kb>
```

or equivalently:

```text
D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe -m tools.kb_validator.validate_kb <your-kb>
```

Exit `0` prints `<your-kb> OK`; exit `1` prints `<your-kb> <error-code>`
with one of the codes in [FORMAT.md](FORMAT.md).

## Worked example

```text
D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe tools\kb_validator\validate_kb.py tests\fixtures\k09b\good
```

prints `tests\fixtures\k09b\good OK` and exits `0`.
Replacing `good` with `no-manifest`, `no-sections`, or `no-purpose` exits
`1` and prints that dir with `KB_MANIFEST_MISSING`, `KB_SECTIONS_MISSING`,
or `KB_PURPOSE_MISSING` respectively.

## Rules to remember

- `manifest.json` must parse as a JSON dict; a missing file, broken JSON,
  or a JSON list/scalar all reject as `KB_MANIFEST_MISSING`.
- Sections mean `.md` files only: `manifest.json` and `purpose.txt` do not
  count, in `sections/` or at the top level.
- Purpose means `purpose.txt` or a non-empty manifest `"purpose"` string;
  an empty or missing string without the file rejects.
