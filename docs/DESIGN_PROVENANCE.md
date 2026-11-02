# Design provenance — FXDESIGN6 icons

Date: 2026-11-02. Lane: FXDESIGN6 (PAIR).

## Material Icons (Apache License 2.0, Google)

Twelve glyphs are copied verbatim as inline SVG path data into
`frontend/src/ui/icons.tsx` (fill currentColor, 24x24 viewBox):

- source archive (READ-ONLY reference, never copied into the repo):
  `D:\AI_PROJECTS\AGENT_SI_KIT\10_DESIGN_SYSTEMS_ASSETS\DESIGN_MATERIAL_ICONS_REFERENCE.zip`
  (material-design-icons-master, Apache-2.0, `LICENSE` at the archive root)
- source files, filled 24px variant (`materialicons/24px.svg`):
  `src/content/add`, `src/file/folder`, `src/action/settings`,
  `src/navigation/expand_more`, `src/navigation/chevron_right`,
  `src/content/send`, `src/editor/attach_file`, `src/av/mic`,
  `src/action/description`, `src/av/play_arrow`, `src/action/visibility`,
  `src/editor/bar_chart` (the reference draws the bars with `rect`
  elements x4/y9/h11, x16/y13/h7, x10/y4/h16, width 4; transcribed as the
  same three bars in path form since `icons.tsx` is path-only)

License: Apache License, Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0).
NOTICE: This product includes Material Icons by Google (Copyright Google Inc.),
licensed under the Apache License 2.0. No modification of the glyph shapes;
only the `bar_chart` rect-to-path transcription described above.

No new npm dependency was added for icons.
