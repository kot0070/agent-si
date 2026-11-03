// FXSMALL item 5 (W13): every project tab (chat + 15 views) shares one hover
// rule in the always-loaded shell stylesheet, so rest and hover never
// compute the same on any route (the chat route never loads
// projectview.css). Asserted from the real stylesheet text.
/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';
import { PROJECT_VIEWS } from '../../projects/projectsApi';

const shellCss = readFileSync('src/ui/shell.css', 'utf8');
const tokensCss = readFileSync('src/ui/tokens.css', 'utf8');

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

function tokenValue(block: string, name: string): string {
  const clean = block.replace(/\/\*[\s\S]*?\*\//g, '');
  const line = clean.split(';').find((l) => l.includes(name));
  return line?.split(':')[1]?.trim() ?? '';
}

function themeBlock(theme: 'dark' | 'light'): string {
  const re = theme === 'dark'
    ? /:root,\s*\[data-theme="dark"\]\s*\{([\s\S]*?)\}/
    : /\[data-theme="light"\]\s*\{([\s\S]*?)\}/;
  return re.exec(tokensCss)?.[1] ?? '';
}

// selector -> normalised declarations for every :hover rule in shell.css.
function hoverRules(): Array<{ selector: string; declarations: string }> {
  const out: Array<{ selector: string; declarations: string }> = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(shellCss)) !== null) {
    if (m[1].includes(':hover')) {
      out.push({
        selector: m[1].replace(/\s+/g, ' ').trim(),
        declarations: m[2].replace(/\/\*[\s\S]*?\*\//g, '').replace(/\s+/g, ' ').trim(),
      });
    }
  }
  return out;
}

const TABS = ['project-chat-tab', ...PROJECT_VIEWS.map((view) => `project-menu-${view}`)];

describe('fxsmall5 W13 one shared tab hover from the real stylesheet', () => {
  it('covers all 16 tabs (chat + 15 views)', () => {
    expect(PROJECT_VIEWS).toHaveLength(15);
    expect(TABS).toHaveLength(16);
  });

  it('one shared hover rule covers every tab with identical declarations', () => {
    const rules = hoverRules();
    const covering = new Map<string, string>();
    for (const tab of TABS) {
      const hits = rules.filter(
        (rule) => rule.selector.includes(`"${tab}"`) || rule.selector.includes(`project-menu-`),
      );
      // The chat tab matches its own quoted testid; every project-menu tab
      // matches the shared prefix selector.
      const mine = tab === 'project-chat-tab'
        ? hits.filter((rule) => rule.selector.includes(`"${tab}"`))
        : hits.filter((rule) => rule.selector.includes('project-menu-'));
      expect(mine.length).toBeGreaterThanOrEqual(1);
      covering.set(tab, mine.map((rule) => rule.declarations).join(' || '));
    }
    // One shared rule: every tab resolves the same declaration text.
    expect(new Set(covering.values()).size).toBe(1);
  });

  it('the shared hover repaints the fill through tokens, >=4.5:1 both themes, no hex', () => {
    const rules = hoverRules();
    const shared = rules.filter(
      (rule) => rule.selector.includes('"project-chat-tab"') && rule.selector.includes('project-menu-'),
    );
    expect(shared).toHaveLength(1);
    const declarations = shared[0]?.declarations ?? '';
    expect(declarations).toMatch(/background-color:\s*var\(--fx-btn-primary-hover\)/);
    expect(declarations).toMatch(/(^|[^-])color:\s*var\(--fx-btn-primary-ink\)/);
    expect(declarations).not.toMatch(/#[0-9a-f]{3,6}/i);
    for (const theme of ['dark', 'light'] as const) {
      const block = themeBlock(theme);
      expect(
        ratio(tokenValue(block, '--fx-btn-primary-ink'), tokenValue(block, '--fx-btn-primary-hover')),
      ).toBeGreaterThanOrEqual(4.5);
    }
  });
});
