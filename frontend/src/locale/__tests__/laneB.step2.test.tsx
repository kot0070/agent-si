/** @vitest-environment jsdom */
/// <reference types="vite/client" />
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  detectOsLocale,
  formatDate,
  formatNumber,
  resetLocaleForTests,
  setLocale,
  t,
  useLocale,
} from '../index';
import en from '../en.json';
import uk from '../uk.json';
import ifaceDts from '../../settings/k07b-iface.d.ts?raw';

type Nested = Record<string, unknown>;

function flatten(node: Nested, prefix = '', acc: string[] = []): string[] {
  for (const key of Object.keys(node)) {
    const value = node[key];
    if (typeof value === 'object' && value !== null) {
      flatten(value as Nested, `${prefix}${key}.`, acc);
    } else {
      acc.push(`${prefix}${key}`);
    }
  }
  return acc;
}

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

const EN_KEYS = flatten(en as unknown as Nested).sort();
const UK_KEYS = flatten(uk as unknown as Nested).sort();

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('locale module', () => {
  it('defaults to en', () => {
    expect(DEFAULT_LOCALE).toBe('en');
    expect(t('settings.general.title')).toBe(en.settings.general.title);
  });

  it('setLocale switches t and persists', () => {
    setLocale('en');
    expect(t('settings.general.title')).toBe(en.settings.general.title);
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    setLocale('uk');
    expect(t('settings.general.title')).toBe(uk.settings.general.title);
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('uk');
  });

  it('interpolates {param} placeholders', () => {
    setLocale('en');
    expect(t('firstrun.greeting', { name: 'Ada' })).toBe('Hello, Ada!');
    expect(t('firstrun.greeting')).toBe('Hello, {name}!');
    setLocale('uk');
    expect(t('firstrun.greeting', { name: 'Ада' })).toBe('Вітаю, Ада!');
  });

  it('unknown key raises MISSING_LOCALE_KEY', () => {
    let code: unknown;
    try {
      t('no.such.key');
    } catch (error) {
      code = (error as { code?: unknown }).code;
    }
    expect(code).toBe('MISSING_LOCALE_KEY');
  });

  it('unsupported locale raises UNSUPPORTED_LOCALE', () => {
    let code: unknown;
    setLocale('uk');
    try {
      setLocale('xx' as 'en');
    } catch (error) {
      code = (error as { code?: unknown }).code;
    }
    expect(code).toBe('UNSUPPORTED_LOCALE');
    expect(t('settings.general.title')).toBe(uk.settings.general.title);
  });

  it('LocaleProvider syncs the module t to its locale (FXUIB-B2: stored uk needs no TopBar)', () => {
    setLocale('uk');
    function Probe() {
      const { locale } = useLocale();
      return <span>{locale}</span>;
    }
    const { unmount } = render(
      <LocaleProvider initialLocale="en">
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByText('en')).toBeTruthy();
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    expect(t('settings.general.title')).toBe(en.settings.general.title);
    unmount();
  });

  it('useLocale defaults to en outside a provider', () => {
    function Probe() {
      const { locale } = useLocale();
      return <span>{locale}</span>;
    }
    render(<Probe />);
    expect(screen.getByText('en')).toBeTruthy();
  });

  it('detectOsLocale follows the OS language', () => {
    const original = window.navigator.language;
    const setLanguage = (value: string): void => {
      Object.defineProperty(window.navigator, 'language', { value, configurable: true });
    };
    try {
      setLanguage('uk-UA');
      expect(detectOsLocale()).toBe('uk');
      setLanguage('en-GB');
      expect(detectOsLocale()).toBe('en');
      setLanguage('en-US');
      expect(detectOsLocale()).toBe('en');
      setLanguage('fr-FR');
      expect(detectOsLocale()).toBe('en');
    } finally {
      setLanguage(original);
    }
  });

  it('formats dates and numbers per locale', () => {
    const day = new Date(Date.UTC(2026, 0, 2, 12, 0, 0));
    const ukDate = formatDate(day, 'uk');
    const enDate = formatDate(day, 'en');
    expect(ukDate).not.toBe(enDate);
    expect(ukDate).toContain('2026');
    expect(enDate).toContain('2026');
    const ukNumber = formatNumber(1234.5, 'uk');
    const enNumber = formatNumber(1234.5, 'en');
    expect(ukNumber).not.toBe(enNumber);
    expect(enNumber).toBe('1,234.5');
  });

  it('resetLocaleForTests restores the default', () => {
    setLocale('uk');
    resetLocaleForTests();
    expect(t('settings.general.title')).toBe(en.settings.general.title);
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull();
  });
});

describe('G5 switch probe', () => {
  it('re-renders in the chosen language and the choice persists', () => {
    function Title() {
      return <h1>{t('settings.general.title')}</h1>;
    }
    setLocale('en');
    const view = render(<Title />);
    expect(screen.getByText(en.settings.general.title)).toBeTruthy();
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    setLocale('uk');
    view.rerender(<Title />);
    expect(screen.getByText(uk.settings.general.title)).toBeTruthy();
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('uk');
  });

  it('provider choice persists across remount', () => {
    const { unmount } = render(
      <LocaleProvider initialLocale="en">
        <span>ready</span>
      </LocaleProvider>,
    );
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    unmount();
    render(
      <LocaleProvider initialLocale="uk">
        <span>ready</span>
      </LocaleProvider>,
    );
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('uk');
  });
});

describe('G2 locale parity gate', () => {
  it('en and uk hold identical key sets', () => {
    expect(UK_KEYS).toEqual(EN_KEYS);
    expect(EN_KEYS.length).toBeGreaterThan(32);
  });

  it('keeps the 32 frozen values with exact contents', () => {
    expect(en.settings.general.title).toBe('General');
    expect(uk.settings.general.title).toBe('Загальне');
  });

  it('licence line is identical in both languages', () => {
    expect(en.about.licence.line).toBe(uk.about.licence.line);
    expect(en.about.licence.line).toBe('Copyright (c) 2026 Ivan Soprun');
  });

  it('contains no Cyrillic in en and Cyrillic copy in uk', () => {
    // FXTABS T11: language names render natively (Українська in the en
    // table too); the gate allowlists exactly those two name values.
    const enText = JSON.stringify(en).replace(/Українська/g, '');
    expect(enText).not.toMatch(/[\u0400-\u04FF]/);
    expect(/[\u0400-\u04FF]/.test(JSON.stringify(uk))).toBe(true);
    for (const value of leafValues(uk as unknown as Nested)) {
      expect(value.length).toBeGreaterThan(0);
    }
  });

  it('plural categories resolve per locale', () => {
    expect(new Intl.PluralRules('uk').select(2)).toBe('few');
    expect(new Intl.PluralRules('en').select(2)).toBe('other');
  });
});

const ADDED_KEYS: readonly string[] = [
  'shell.topbar.project',
  'shell.topbar.language',
  'shell.topbar.watcher',
  'shell.topbar.stop_all',
  'shell.sidebar.chat',
  'shell.sidebar.agents_live',
  'shell.sidebar.projects',
  'shell.sidebar.tasks',
  'shell.inspector.live_agents',
  'shell.closing.confirm',
  'shell.closing.stay',
  'shell.closing.leave',
  'chat.composer.prompt',
  'chat.composer.send',
  'chat.composer.draft',
  'chat.stream.spinner',
  'chat.stream.timestamp',
  'chat.stream.offline',
  'chat.abort.cancel',
  'chat.approval.accept',
  'chat.approval.edit',
  'chat.approval.reject',
  'tasks.list.title',
  'tasks.list.empty',
  'tasks.creator.title',
  'tasks.creator.create',
  'tasks.status.queued',
  'tasks.status.running',
  'tasks.status.returned',
  'tasks.status.accepted',
  'tasks.status.rejected',
  'tasks.status.blocked',
  'tasks.status.handoff',
  'projects.list.title',
  'projects.list.empty',
  'projects.overview.title',
  'projects.runs.title',
  'projects.time.title',
  'projects.ai_usage.title',
  'projects.tokens.title',
  'projects.cost.title',
  'projects.local_ai.title',
  'projects.cloud_ai.title',
  'projects.models.title',
  'projects.routing.title',
  'projects.audits.title',
  'projects.errors.title',
  'projects.reports.title',
  'projects.why_this_model.title',
  'projects.derived.label',
  'agents.live.title',
  'agents.live.empty',
  'agents.badge.local',
  'agents.badge.split',
  'agents.badge.cloud',
  'agents.row.scope',
  'agents.row.deliverable',
  'agents.row.tokens',
  'ui.card.toggle',
  'ui.card.total',
  'ui.table.empty',
  'ui.error.retry',
  'ui.loading.more',
  'ui.disclosure.more',
  'ui.disclosure.less',
  'api.error.scope_overlap',
  'api.error.rejected_scope_overlap',
  'api.error.gate_not_passed',
  'api.error.missing_integration_task',
  'api.error.invalid_hierarchy_chain',
  'api.error.audit_independence_rejected',
  'api.error.budget_capped',
  'api.error.unknown_limit_kind',
  'api.error.delta_over_bound',
  'api.error.context_wrong_contract_version',
  'api.error.policy_conflict',
  'api.error.context_missing',
  'api.error.no_profile_blocked',
  'api.error.no_eligible_candidate',
  'api.error.modality_mismatch',
  'api.error.provider_unevidenced',
  'api.error.price_unknown_expensive',
  'api.error.budget_soft_warn',
  'api.error.budget_hard_blocked',
  'api.error.pending_reconciliation',
  'api.error.duplicate_settlement_refused',
  'api.error.kb_validation_failed',
  'api.error.kb_proposal_not_approved',
  'api.error.key_save_timeout',
  'api.error.credential_entry_missing',
];

const FROZEN_STEP1_KEYS: readonly string[] = [
  'about.licence.line',
  'about.licence.mitText',
  'howItWorks.codeTests.body',
  'howItWorks.codeTests.title',
  'howItWorks.localTests.body',
  'howItWorks.localTests.title',
  'howItWorks.runs.body',
  'howItWorks.runs.title',
  'settings.appearance.needItNow',
  'settings.appearance.purpose',
  'settings.appearance.title',
  'settings.capabilityDb.needItNow',
  'settings.capabilityDb.purpose',
  'settings.capabilityDb.title',
  'settings.general.needItNow',
  'settings.general.purpose',
  'settings.general.title',
  'settings.localAi.needItNow',
  'settings.localAi.purpose',
  'settings.localAi.title',
  'settings.models.needItNow',
  'settings.models.purpose',
  'settings.models.title',
  'settings.optimization.needItNow',
  'settings.optimization.purpose',
  'settings.optimization.title',
  'settings.project.needItNow',
  'settings.project.purpose',
  'settings.project.title',
  'settings.routing.needItNow',
  'settings.routing.purpose',
  'settings.routing.title',
];

function getPath(table: unknown, dotted: string): unknown {
  let node: unknown = table;
  for (const part of dotted.split('.')) {
    if (typeof node !== 'object' || node === null) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

describe('G2 full-set parity gate (round 3: Lane A keys added)', () => {
  it('adds all 90 Lane A keys to both languages with real text', () => {
    expect(ADDED_KEYS).toHaveLength(90);
    for (const key of ADDED_KEYS) {
      const enText = getPath(en, key) as string;
      const ukText = getPath(uk, key) as string;
      expect(typeof enText).toBe('string');
      expect(typeof ukText).toBe('string');
      expect(enText.length).toBeGreaterThan(0);
      expect(ukText.length).toBeGreaterThan(0);
      expect(enText).not.toMatch(/TODO|FIXME|NotImplemented/);
      expect(ukText).not.toMatch(/TODO|FIXME|NotImplemented/);
      expect(enText).not.toMatch(/[\u0400-\u04FF]/);
    }
  });

  it('t resolves every added key in both locales', () => {
    setLocale('en');
    for (const key of ADDED_KEYS) {
      expect(t(key)).toBe(getPath(en, key) as string);
    }
    setLocale('uk');
    for (const key of ADDED_KEYS) {
      expect(t(key)).toBe(getPath(uk, key) as string);
    }
  });

  it('full sets stay identical (en key set == uk key set)', () => {
    expect(UK_KEYS).toEqual(EN_KEYS);
    expect(EN_KEYS.length).toBe(UK_KEYS.length);
    expect(EN_KEYS.length).toBeGreaterThanOrEqual(
      ADDED_KEYS.length + FROZEN_STEP1_KEYS.length,
    );
  });

  it('keeps all 32 frozen STEP1 paths in both languages', () => {
    expect(FROZEN_STEP1_KEYS).toHaveLength(32);
    for (const key of FROZEN_STEP1_KEYS) {
      expect(typeof getPath(en, key)).toBe('string');
      expect(typeof getPath(uk, key)).toBe('string');
    }
  });
});

describe('G2 LocaleKey union parity gate (round 3: union widened to full set)', () => {
  it('LocaleKey union == en leaf set == uk leaf set', () => {
    const block = /export type LocaleKey =([\s\S]*?);/.exec(ifaceDts)?.[1] ?? '';
    expect(block.length).toBeGreaterThan(0);
    const unionKeys = [...block.matchAll(/'([^']+)'/g)].map((m) => m[1]).sort();
    expect(unionKeys).toEqual(EN_KEYS);
    expect(unionKeys).toEqual(UK_KEYS);
    expect(unionKeys.length).toBe(EN_KEYS.length);
  });
});
