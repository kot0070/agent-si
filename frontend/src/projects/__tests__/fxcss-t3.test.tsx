// FXCSS: the FXTABS T3 comment was left unclosed, commenting out the
// .fxpv-fact / .fxpv-note / .fxpv-row short-cell rules until the U2 close.
// Strip CSS comments and assert those rules are live (RED on the old file).
/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';

const css = readFileSync('src/projects/projectview.css', 'utf8');
const live = css.replace(/\/\*[\s\S]*?\*\//g, '');

describe('FXCSS T3 comment close: short-cell rules live', () => {
  it('.fxpv-fact short-cell rule is live with tabular numbers', () => {
    expect(live).toMatch(/^\.fxpv-fact\s*\{/m);
    expect(live).toMatch(
      /\.fxpv-fact-value[^}]*font-variant-numeric:\s*tabular-nums/,
    );
  });

  it('.fxpv-note and standalone .fxpv-row rules are live', () => {
    expect(live).toMatch(/^\.fxpv-note\s*\{/m);
    expect(live).toMatch(/^\.fxpv-row\s*\{/m);
  });

  it('U2 placement rules still live', () => {
    expect(live).toMatch(/^\.fxpv-place\s*\{/m);
  });
});
