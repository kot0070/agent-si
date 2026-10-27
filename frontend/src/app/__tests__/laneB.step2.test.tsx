/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { FirstRunFlow } from '../firstrun/FirstRunFlow';
import { About, AGENT_SI_NAME, APP_ID, LICENCE_LINE, MIT_LICENSE_REF } from '../About';
import { MigrationView, runMigration } from '../migration/MigrationView';
import { HOW_IT_WORKS_KEYS, HowItWorks } from '../HowItWorks';
import { SettingsLayout } from '../../shell/SettingsLayout';
import { SETTINGS_ROUTES } from '../../settings/index';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import en from '../../locale/en.json';
import uk from '../../locale/uk.json';

type Nested = Record<string, unknown>;

function leafValues(node: Nested, acc: string[] = []): string[] {
  for (const key of Object.keys(node)) {
    const value = node[key];
    if (typeof value === 'object' && value !== null) {
      leafValues(value as Nested, acc);
    } else {
      acc.push(value as string);
    }
  }
  return acc;
}

const ALLOWED_TEXT = new Set<string>([
  ...leafValues(en as unknown as Nested),
  ...leafValues(uk as unknown as Nested),
  AGENT_SI_NAME,
  LICENCE_LINE,
  ...Object.values(HOW_IT_WORKS_KEYS),
]);

function visibleTexts(container: HTMLElement): string[] {
  const walker = container.ownerDocument.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const out: string[] = [];
  let node = walker.nextNode();
  while (node) {
    const text = (node.textContent ?? '').trim();
    if (text.length > 0) {
      out.push(text);
    }
    node = walker.nextNode();
  }
  return out;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('FirstRunFlow', () => {
  it('covers the required steps and skippable optionals, one Next click completes', () => {
    let done = false;
    const { container } = render(<FirstRunFlow onComplete={() => { done = true; }} />);
    expect(screen.getByText(en.firstrun.title)).toBeTruthy();
    for (const step of Object.values(en.firstrun.steps)) {
      expect(screen.getByText(step)).toBeTruthy();
    }
    const skips = screen.getAllByRole('button', { name: en.firstrun.skip });
    expect(skips.length).toBe(4);
    fireEvent.click(skips[0]!);
    expect(screen.getAllByRole('button', { name: en.firstrun.skip }).length).toBe(3);
    expect(done).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(done).toBe(true);
    expect(container.textContent).toContain(en.firstrun.optionalNote);
  });
});

describe('G8 name probe', () => {
  it('exposes the product name and app id', () => {
    expect(APP_ID).toBe('com.agentsi.app');
    expect(AGENT_SI_NAME).toBe('Agent SI');
    render(<About />);
    expect(screen.getByText(AGENT_SI_NAME)).toBeTruthy();
  });
});

describe('G7 licence probe', () => {
  it('shows the licence line and MIT text in both languages', () => {
    const english = render(<About locale="en" />);
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    expect(english.container.textContent).toContain(en.about.licence.mitText);
    cleanup();
    const ukrainian = render(<About locale="uk" />);
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    expect(ukrainian.container.textContent).toContain(uk.about.licence.mitText);
    expect(MIT_LICENSE_REF).toBe('about.licence.mitText');
  });
});

describe('migration', () => {
  it('view states that old copies are kept and runMigration reports them', async () => {
    render(<MigrationView projectId="project-1" />);
    expect(screen.getByText(en.migration.keepsOldCopies)).toBeTruthy();
    const result = await runMigration('project-1');
    expect(result).toEqual({ migrated: true, oldCopiesKept: true });
    expect(window.localStorage.getItem('agentsi.migrated.project-1')).toBe('true');
  });
});

describe('G6 explainer probe', () => {
  it('explains runs vs code tests vs local tests in both languages with key ids visible', () => {
    const english = render(<HowItWorks locale="en" />);
    expect(english.container.textContent).toContain(en.howItWorks.runs.title);
    expect(english.container.textContent).toContain(en.howItWorks.runs.body);
    expect(english.container.textContent).toContain(en.howItWorks.codeTests.body);
    expect(english.container.textContent).toContain(en.howItWorks.localTests.body);
    for (const key of Object.values(HOW_IT_WORKS_KEYS)) {
      expect(screen.getByText(key)).toBeTruthy();
    }
    cleanup();
    const ukrainian = render(<HowItWorks locale="uk" />);
    expect(ukrainian.container.textContent).toContain(uk.howItWorks.runs.title);
    expect(ukrainian.container.textContent).toContain(uk.howItWorks.runs.body);
    expect(ukrainian.container.textContent).toContain(uk.howItWorks.codeTests.body);
    expect(ukrainian.container.textContent).toContain(uk.howItWorks.localTests.body);
    for (const key of Object.values(HOW_IT_WORKS_KEYS)) {
      expect(screen.getByText(key)).toBeTruthy();
    }
  });
});

describe('literal scan', () => {
  it('renders no hard-coded visible strings outside locale files', () => {
    const route = SETTINGS_ROUTES[0]!;
    const views = [
      render(
        <SettingsLayout
          titleKey={route.titleKey}
          purposeKey={route.purposeKey}
          needItNowKey={route.needItNowKey}
        >
          <span>{en.empty.generic}</span>
        </SettingsLayout>,
      ),
      render(<FirstRunFlow onComplete={() => undefined} />),
      render(<About />),
      render(<MigrationView projectId="project-1" />),
      render(<HowItWorks />),
    ];
    const stray: string[] = [];
    for (const view of views) {
      for (const text of visibleTexts(view.container)) {
        if (!ALLOWED_TEXT.has(text)) {
          stray.push(text);
        }
      }
      view.unmount();
    }
    expect(stray).toEqual([]);
  });
});
