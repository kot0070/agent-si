/** @vitest-environment jsdom */
// FXLOCALE2: every new UI label key (S1 chat.hierarchy.*, S2 subtitles,
// S3 scanner-visible rows, S4 TestsTab/ProjectView) resolves in en + uk.
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup } from '@testing-library/react';
import { resetLocaleForTests, setLocale, t } from '../index';
import { projectViewTitleKey } from '../../projects/projectsApi';

const S1_KEYS: readonly string[] = [
  'chat.hierarchy.title',
  'chat.hierarchy.director',
  'chat.hierarchy.manager',
  'chat.hierarchy.agents',
  'chat.hierarchy.auto',
  'chat.hierarchy.expand',
  'chat.hierarchy.collapse',
  'chat.hierarchy.connect',
  'chat.hierarchy.noProject',
  'chat.hierarchy.auditorSplit',
  'chat.hierarchy.openSettings',
];

const S2_KEYS: readonly string[] = [
  'tasks.creator.subtitle',
  'projects.list.subtitle',
  'projects.reports.subtitle',
  'settings.index.subtitle',
  'watcher.tab.subtitle',
  'agents.live.subtitle',
];

const S3_KEYS: readonly string[] = [
  'telemetry.model',
  'telemetry.calls',
  'telemetry.tokens',
  'telemetry.cost',
  'telemetry.provider',
  'telemetry.project',
  'telemetry.tasks',
  'telemetry.audits',
  'telemetry.perModel',
  'telemetry.perProvider',
  'telemetry.unavailable',
  'watcher.tab.loading',
  'watcher.tab.ok',
  'watcher.tab.failed',
  'watcher.tab.settings',
  'watcher.tab.model',
  'watcher.tab.cloudFallback',
];

const S4_KEYS: readonly string[] = [
  'projects.tests.title',
  'projects.tests.explainer',
  'projects.tests.emptyHow',
  'projects.tests.counter.active',
  'projects.tests.counter.passed',
  'projects.tests.counter.remaining',
  'projects.tests.showOutput',
  'projects.tests.hideOutput',
  'projects.tests.kind.code',
  'projects.tests.kind.ai',
  'projects.tests.kind.human',
  'projects.tests.kind.unknown',
  'projects.tests.local.title',
  'projects.tests.local.body',
  'projects.tests.local.label',
  'projects.tests.local.on',
  'projects.tests.local.off',
];

const ALL_KEYS: readonly string[] = [
  ...S1_KEYS,
  ...S2_KEYS,
  ...S3_KEYS,
  ...S4_KEYS,
];

// Locale-neutral tokens, identical in both tables by design.
const SAME_IN_BOTH: ReadonlySet<string> = new Set([
  'watcher.tab.ok',
  'projects.tests.kind.ai',
]);

const EN_DEFAULTS: Readonly<Record<string, string>> = {
  'chat.hierarchy.title': 'Model hierarchy',
  'chat.hierarchy.director': 'Director',
  'chat.hierarchy.manager': 'Manager',
  'chat.hierarchy.agents': 'Agents',
  'chat.hierarchy.auto': 'Auto',
  'chat.hierarchy.expand': 'Show model hierarchy',
  'chat.hierarchy.collapse': 'Hide model hierarchy',
  'chat.hierarchy.connect': 'Connect a provider',
  'chat.hierarchy.noProject': 'Choose a project to set the model hierarchy.',
  'chat.hierarchy.auditorSplit': 'The auditor uses a different provider.',
  'chat.hierarchy.openSettings': 'Open Settings',
  'tasks.creator.subtitle':
    'Start here: one message creates the first project and task.',
  'projects.list.subtitle': 'Every project in one list; open one to work.',
  'projects.reports.subtitle': 'Latest reports with files, ready to open.',
  'settings.index.subtitle':
    'Defaults live here; open only the page you need.',
  'watcher.tab.subtitle':
    'Independent watch over agents: state, journal and rules.',
  'agents.live.subtitle': 'Who works on what right now, updating live.',
  'telemetry.model': 'Model',
  'telemetry.calls': 'Calls',
  'telemetry.tokens': 'Tokens',
  'telemetry.cost': 'Cost',
  'telemetry.provider': 'Provider',
  'telemetry.project': 'Project',
  'telemetry.tasks': 'Tasks',
  'telemetry.audits': 'Audits',
  'telemetry.perModel': 'Per-model',
  'telemetry.perProvider': 'Per-provider',
  'telemetry.unavailable': 'UNAVAILABLE',
  'watcher.tab.loading': 'Loading...',
  'watcher.tab.ok': 'OK',
  'watcher.tab.failed': 'FAILED',
  'watcher.tab.settings': 'Watcher settings',
  'watcher.tab.model': 'Model',
  'watcher.tab.cloudFallback': 'Cloud fallback',
  'projects.tests.title': 'Tests',
  'projects.tests.counter.active': 'active',
  'projects.tests.counter.passed': 'passed',
  'projects.tests.counter.remaining': 'remaining',
  'projects.tests.showOutput': 'Show output',
  'projects.tests.hideOutput': 'Hide output',
  'projects.tests.kind.code': 'code',
  'projects.tests.kind.ai': 'AI',
  'projects.tests.kind.human': 'human',
  'projects.tests.kind.unknown': 'unknown',
  'projects.tests.local.title': 'Local tests',
  'projects.tests.local.label': 'Local tests',
  'projects.tests.local.on': 'on',
  'projects.tests.local.off': 'off',
};

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('fxlocale2 new-label keys', () => {
  it('resolves every S1/S2/S3-visible/S4 key in English', () => {
    setLocale('en');
    for (const key of ALL_KEYS) {
      const text = t(key);
      expect(typeof text).toBe('string');
      expect(text.length).toBeGreaterThan(0);
      expect(text).not.toMatch(/[\u0400-\u04FF]/);
    }
  });

  it('resolves every S1/S2/S3-visible/S4 key in Ukrainian', () => {
    setLocale('uk');
    for (const key of ALL_KEYS) {
      const text = t(key);
      expect(typeof text).toBe('string');
      expect(text.length).toBeGreaterThan(0);
    }
  });

  it('renders Ukrainian (not English) in uk mode outside neutral tokens', () => {
    setLocale('en');
    const english = new Map(ALL_KEYS.map((key) => [key, t(key)] as const));
    setLocale('uk');
    for (const key of ALL_KEYS) {
      if (SAME_IN_BOTH.has(key)) {
        expect(t(key)).toBe(english.get(key));
      } else {
        expect(t(key)).not.toBe(english.get(key));
      }
    }
  });

  it('keeps the specified English defaults verbatim', () => {
    setLocale('en');
    for (const [key, expected] of Object.entries(EN_DEFAULTS)) {
      expect(t(key)).toBe(expected);
    }
  });

  it('routes the tests view title through projects.tests.title', () => {
    expect(projectViewTitleKey('tests')).toBe('projects.tests.title');
    setLocale('en');
    expect(t(projectViewTitleKey('tests'))).toBe('Tests');
    setLocale('uk');
    expect(t(projectViewTitleKey('tests'))).toBe('Тести');
  });
});
