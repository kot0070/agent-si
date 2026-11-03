// FXLOOK D1 supersedes U1: 16 tabs in 3 wrapped rows hid the working
// area, so the strip is ONE scrolled row (nowrap lane + arrows), never
// wrapped text. Reason: owner-found D1 (tabs wrapped to ~200px/3 rows).
/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';

const css = readFileSync('src/projects/projectview.css', 'utf8');

describe('U1 quiet wrapping tab strip', () => {
  it('tab row never wraps: one nowrap lane with sideways scroll', () => {
    expect(css).toMatch(/\.fxpv-tabs\s*\{[^}]*flex-wrap:\s*nowrap/);
    expect(css).toMatch(/\.fxpv-tabs-scroll\s*\{[^}]*overflow-x:\s*auto/);
  });

  it('tabs are quiet text: no box, no solid repaint on hover', () => {
    // FXTABS spells the same behaviour with background-color and a
    // transparent border; both read as "no box, no repaint".
    expect(css).toMatch(/\.fxpv-tab\s*\{[^}]*background(-color)?:\s*transparent/);
    expect(css).toMatch(/\.fxpv-tab\s*\{[^}]*border:\s*(none|1px solid transparent)/);
    expect(css).toMatch(
      /\.fxpv-tabs \.fxpv-tab:hover:not\(:disabled\)\s*\{[^}]*background(-color)?:\s*transparent/,
    );
  });

  it('selected tab is bold + underline in ink, readable in both themes', () => {
    expect(css).toMatch(/\.fxpv-tab-selected\s*\{[^}]*font-weight:\s*700/);
    expect(css).toMatch(/\.fxpv-tab-selected\s*\{[^}]*text-decoration:\s*underline/);
    expect(css).toMatch(/\.fxpv-tab-selected\s*\{[^}]*color:\s*var\(--fx-ink/);
  });
});
