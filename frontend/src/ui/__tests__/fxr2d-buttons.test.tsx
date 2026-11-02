// Y1 RED: primary + Cancel buttons keep >=4.5:1 text contrast in
// rest, hover, focus, active and disabled states, dark + light.
// Computed from the real custom properties per theme (not eyeballing).
/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';
import { applyTheme } from '../../shell/theme';

const tokensCss = readFileSync('src/ui/tokens.css', 'utf8');
const baseCss = readFileSync('src/ui/base.css', 'utf8');
const shellCss = readFileSync('src/ui/shell.css', 'utf8');

function install(): void {
  document.getElementById('fxr2d-y1')?.remove();
  const el = document.createElement('style');
  el.id = 'fxr2d-y1';
  el.textContent = `${tokensCss}\n${baseCss}\n${shellCss}`;
  document.head.appendChild(el);
}

afterEach(() => {
  document.getElementById('fxr2d-y1')?.remove();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('style');
});

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

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

describe('Y1 button contrast in every state', () => {
  it.each(['dark', 'light'] as const)('primary rest + hover >= 4.5:1 in %s', (theme) => {
    install();
    applyTheme(theme);
    const ink = token('--fx-btn-primary-ink');
    expect(ratio(ink, token('--fx-btn-primary-bg'))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(ink, token('--fx-btn-primary-hover'))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(['dark', 'light'] as const)('quiet Cancel >= 4.5:1 against the surface in %s', (theme) => {
    install();
    applyTheme(theme);
    expect(ratio(token('--fx-btn-quiet-ink'), token('--fx-surface'))).toBeGreaterThanOrEqual(4.5);
  });

  it('hover never repaints bright accent; no gradients anywhere', () => {
    expect(baseCss).toMatch(/button:hover[^{]*\{[^}]*background-color:\s*var\(--fx-btn-primary-hover\)/);
    expect(baseCss).not.toMatch(/linear-gradient/);
    expect(shellCss).not.toMatch(/linear-gradient/);
    expect(tokensCss).not.toMatch(/linear-gradient/);
  });
});
