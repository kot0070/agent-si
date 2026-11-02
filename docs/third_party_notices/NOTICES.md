# Third-party notices — Agent SI

Project licence: MIT, Copyright (c) 2026 Ivan Soprun. See `LICENSE` at the checkout root. The About screen shows the product name, the copyright line, the licence text, and the third-party list.

This file lists every third-party component shipped with the release. Versions come from the lock files: `frontend/package-lock.json` for the interface and `pyproject.toml` plus the frozen sidecar metadata for the desktop bundle. Texts for components that need them are vendored in `licenses/`.

## Interface runtime

| component | version | licence | source |
| --------- | ------- | ------- | ------ |
| react | 19.3.1 | MIT | frontend/package.json and frontend/package-lock.json |
| react-router-dom | 7.18.4 | MIT | frontend/package.json and frontend/package-lock.json |
| zod | 4.6.7 | MIT | frontend/package.json and frontend/package-lock.json |

## Backend runtime

| component | version | licence | source |
| --------- | ------- | ------- | ------ |
| fastapi | 0.162.0 | MIT | pyproject.toml |
| openai-agents | 0.20.0 | MIT | pyproject.toml |

## Desktop bundle sidecar

| component | version | licence | source |
| --------- | ------- | ------- | ------ |
| pywebview | 6.2.1 | BSD 3-Clause | installed bundle metadata |
| pythonnet | 3.2.1 | MIT | installed bundle metadata |
| clr_loader | 0.3.1 | MIT | installed bundle metadata |
| bottle | 0.13.4 | MIT | installed bundle metadata |
| proxy_tools | 0.1.0 | MIT | installed bundle metadata |

## Icons

Material Icons by Google, Apache License, Version 2.0. Twelve glyphs used as inline SVG paths. See `docs/DESIGN_PROVENANCE.md`.

## Licence texts

- `licenses/MIT_LICENSE.txt` — project licence text, identical to root `LICENSE`.
- `licenses/LICENSE.pywebview` — pywebview licence text.
- `licenses/LICENSE.pythonnet` — pythonnet licence text.
- `licenses/LICENSE.clr_loader` — clr_loader licence text.
- `licenses/LICENSE.bottle` — bottle licence text.
- proxy_tools — MIT per installed metadata; no separate text file ships in the bundle.

<<FINAL: regenerate this table from the lock files at release time and confirm each licence text is present in the bundle>>
