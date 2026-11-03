// FXSMALL item 4 (W04): theme-toggle hover + topbar-language reach >=4.5:1
// through theme tokens only (no one-off colours), asserted from the real
// stylesheets: token-pair math per theme plus the rules that wire them.
/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';

const tokensCss = readFileSync('src/ui/tokens.css', 'utf8');
const shellCss = readFileSync('src/ui/shell.css', 'utf8');

function lum(hex: string): number {
  const c = hex.trim();
  const r = parseInt(c.slice(1, 3), 16) / 255;
  const g = parseInt(c.slice(3, 5), 16) / 255;
  const b = parseInt(c.slice(5, 7), 16) / 255;
  const f = (v: number): number => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(fg: string, bg: string): number {
  const a = lum(fg);
  const b = lum(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

// One theme block ([data-theme="dark"] or [data-theme="light"]): resolve a
// --token name to its hex value.
function tokenValue(theme: 'dark' | 'light', name: string): string {
  const blockRe = theme === 'dark'
    ? /:root,\s*\[data-theme="dark"\]\s*\{([\s\S]*?)\}/
    : /\[data-theme="light"\]\s*\{([\s\S]*?)\}/;
  const body = blockRe.exec(tokensCss)?.[1] ?? '';
  const clean = body.replace(/\/\*[\s\S]*?\*\//g, '');
  const line = clean.split(';').find((l) => l.includes(name));
  const value = line?.split(':')[1]?.trim() ?? '';
  expect(value).toMatch(/^#[0-9a-f]{6}$/i);
  return value;
}

// All CSS rule blocks whose selector text contains `needle`.
function blocksWith(selectorNeedle: string): string[] {
  const out: string[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(shellCss)) !== null) {
    if (m[1].includes(selectorNeedle)) {
      out.push(`${m[1].trim()} {${m[2].trim()}}`);
    }
  }
  return out;
}

describe('fxsmall4 W04 token contrast from the real stylesheets', () => {
  it.each(['dark', 'light'] as const)('toggle-hover pair (primary ink on primary-hover) >= 4.5:1 in %s', (theme) => {
    expect(ratio(tokenValue(theme, '--fx-btn-primary-ink'), tokenValue(theme, '--fx-btn-primary-hover'))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['dark', 'light'] as const)('language-select pair (ink on surface) >= 4.5:1 in %s', (theme) => {
    expect(ratio(tokenValue(theme, '--fx-ink'), tokenValue(theme, '--fx-surface'))).toBeGreaterThanOrEqual(4.5);
  });

  it('theme-toggle hover wires exactly that token pair, no hex', () => {
    const hits = blocksWith('theme-toggle');
    const hover = hits.filter((b) => b.includes(':hover'));
    expect(hover.length).toBeGreaterThanOrEqual(1);
    const rule = hover.join('\n');
    expect(rule).toMatch(/background-color:\s*var\(--fx-btn-primary-hover\)/);
    expect(rule).toMatch(/(^|[^-])color:\s*var\(--fx-btn-primary-ink\)/);
    expect(rule).not.toMatch(/#[0-9a-f]{3,6}/i);
  });

  it('language select paints an opaque token background, no hex', () => {
    const hits = blocksWith('.fx-topbar-language');
    expect(hits.length).toBeGreaterThanOrEqual(1);
    const rule = hits.join('\n');
    expect(rule).toMatch(/background-color:\s*var\(--fx-[a-z-]+\)/);
    expect(rule).not.toMatch(/#[0-9a-f]{3,6}/i);
    // The wired token really is the asserted pair.
    const token = /background-color:\s*(var\(--fx-[a-z-]+\))/.exec(rule)?.[1] ?? '';
    expect(token).toBe('var(--fx-surface)');
  });
});
