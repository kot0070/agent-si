// U12: native select popups follow the active theme. The highlighted
// option must never paint an unreadable square: color-scheme is set per
// theme on :root and option colors come from tokens for every native
// select (language, project, mode, model, strategy, watcher).
/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';
import { applyTheme } from '../../shell/theme';

const tokensCss = readFileSync('src/ui/tokens.css', 'utf8');
const baseCss = readFileSync('src/ui/base.css', 'utf8');
function install(): void {
  document.getElementById('fxr2d-u12')?.remove();
  const el = document.createElement('style');
  el.id = 'fxr2d-u12';
  el.textContent = `${tokensCss}\n${baseCss}`;
  document.head.appendChild(el);
}

afterEach(() => {
  document.getElementById('fxr2d-u12')?.remove();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('style');
});

describe('U12 native select popup theming', () => {
  it('computed color-scheme on :root follows the theme', () => {
    install();
    applyTheme('dark');
    expect(getComputedStyle(document.documentElement).colorScheme).toBe('dark');
    applyTheme('light');
    expect(getComputedStyle(document.documentElement).colorScheme).toBe('light');
  });

  it('option colors come from tokens; no static scheme overrides the theme', () => {
    expect(tokensCss).toMatch(/select option[\s\S]*?background-color:\s*var\(--fx-input-bg\)/);
    expect(tokensCss).toMatch(/select option[\s\S]*?color:\s*var\(--fx-ink\)/);
    expect(baseCss).not.toMatch(/^\s*color-scheme\s*:/m);
  });
});
