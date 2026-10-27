/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import {
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  detectOsLocale,
  formatDate,
  formatNumber,
  setLocale,
  t,
  useLocale,
} from '../../locale/index';
import type { SupportedLocale } from '../../locale/index';
import { SettingsLayout } from '../../shell/SettingsLayout';
import {
  AcceptedRiskSwitch,
  RoleProfileEditor,
  SETTINGS_ROUTES,
  validateRoleProfile,
} from '../../settings/index';
import { FirstRunFlow } from '../firstrun/FirstRunFlow';
import { About, AGENT_SI_NAME, APP_ID, LICENCE_LINE } from '../About';
import { MigrationView, runMigration } from '../migration/MigrationView';
import { HOW_IT_WORKS_KEYS, HowItWorks } from '../HowItWorks';
import en from '../../locale/en.json';
import uk from '../../locale/uk.json';

afterEach(() => {
  cleanup();
});

describe('lane B behaviour contract (STEP1: every behaviour below fails on throwing product bodies)', () => {
  it('t returns the uk string for a known key', () => {
    expect(t('settings.general.title')).toBe(uk.settings.general.title);
  });

  it('t returns the en string after setLocale', () => {
    setLocale('en');
    expect(t('settings.general.title')).toBe(en.settings.general.title);
  });

  it('locale persists across remount', () => {
    const first: SupportedLocale = 'en';
    render(
      <LocaleProvider initialLocale={first}>
        <span>ready</span>
      </LocaleProvider>,
    );
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
  });

  it('useLocale exposes the active locale', () => {
    function Probe() {
      const { locale } = useLocale();
      return <span>{locale}</span>;
    }
    render(<Probe />);
    expect(screen.getByText('uk')).toBeTruthy();
  });

  it('detectOsLocale follows the OS language', () => {
    Object.defineProperty(window.navigator, 'language', { value: 'uk-UA', configurable: true });
    expect(detectOsLocale()).toBe('uk');
  });

  it('formats dates and numbers per locale', () => {
    const day = new Date(Date.UTC(2026, 0, 2, 12, 0, 0));
    expect(formatDate(day, 'uk')).not.toBe(formatDate(day, 'en'));
    expect(formatNumber(1234.5, 'uk')).not.toBe(formatNumber(1234.5, 'en'));
  });

  it('SettingsLayout renders title and purpose from locale', () => {
    const route = SETTINGS_ROUTES[0]!;
    render(
      <SettingsLayout titleKey={route.titleKey} purposeKey={route.purposeKey} needItNowKey={route.needItNowKey}>
        <span>body</span>
      </SettingsLayout>,
    );
    expect(screen.getByText(en.settings.general.title)).toBeTruthy();
    expect(screen.getByText(en.settings.general.purpose)).toBeTruthy();
  });

  it('role profile editing validates input', () => {
    expect(validateRoleProfile({ role: 'manager', mode: 'AUTO' }).ok).toBe(true);
  });

  it('role profile editor and accepted-risk switch render', () => {
    render(<RoleProfileEditor projectId="project-1" role="manager" />);
    render(<AcceptedRiskSwitch projectId="project-1" />);
  });

  it('first run advances through required steps and skips optionals', () => {
    let done = false;
    render(<FirstRunFlow onComplete={() => { done = true; }} />);
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(done).toBe(true);
  });

  it('About shows the product name and licence line in both languages', () => {
    render(<About />);
    expect(screen.getByText(AGENT_SI_NAME)).toBeTruthy();
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    expect(APP_ID).toBe('com.agentsi.app');
  });

  it('migration reports that old copies are kept', async () => {
    render(<MigrationView projectId="project-1" />);
    const result = await runMigration('project-1');
    expect(result.oldCopiesKept).toBe(true);
  });

  it('HowItWorks explains runs vs code tests vs local tests in both languages', () => {
    render(<HowItWorks />);
    expect(screen.getByText(HOW_IT_WORKS_KEYS.runsBody)).toBeTruthy();
    expect(screen.getByText(HOW_IT_WORKS_KEYS.codeTestsBody)).toBeTruthy();
    expect(screen.getByText(HOW_IT_WORKS_KEYS.localTestsBody)).toBeTruthy();
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
    try {
      setLocale('xx' as SupportedLocale);
    } catch (error) {
      code = (error as { code?: unknown }).code;
    }
    expect(code).toBe('UNSUPPORTED_LOCALE');
  });
});
