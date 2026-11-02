// U1: project tab strip reads as quiet text tabs that wrap to more
// lines — no boxed scroll row, no thick scrollbar, no solid repaint.
/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';

const css = readFileSync('src/projects/projectview.css', 'utf8');

describe('U1 quiet wrapping tab strip', () => {
  it('tab row wraps with no sideways scroll', () => {
    expect(css).toMatch(/\.fxpv-tabs\s*\{[^}]*flex-wrap:\s*wrap/);
    expect(css).toMatch(/\.fxpv-tabs\s*\{[^}]*overflow-x:\s*visible/);
  });

  it('tabs are quiet text: no box, no solid repaint on hover', () => {
    expect(css).toMatch(/\.fxpv-tab\s*\{[^}]*background:\s*transparent/);
    expect(css).toMatch(/\.fxpv-tab\s*\{[^}]*border:\s*none/);
    expect(css).toMatch(
      /\.fxpv-tabs \.fxpv-tab:hover:not\(:disabled\)\s*\{[^}]*background:\s*transparent/,
    );
  });

  it('selected tab is bold + underline in ink, readable in both themes', () => {
    expect(css).toMatch(/\.fxpv-tab-selected\s*\{[^}]*font-weight:\s*700/);
    expect(css).toMatch(/\.fxpv-tab-selected\s*\{[^}]*text-decoration:\s*underline/);
    expect(css).toMatch(/\.fxpv-tab-selected\s*\{[^}]*color:\s*var\(--fx-ink\)/);
  });
});
