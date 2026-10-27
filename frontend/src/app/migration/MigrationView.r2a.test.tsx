/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { ApiClientProvider } from '../ApiClientProvider';
import { FakeApiClient } from '../../api/client';
import { resetLocaleForTests, setLocale, t } from '../../locale/index';
import { App } from '../App';

const LEGACY_SETTINGS = 'agentsi.legacy.p-1.settings';
const NEW_SETTINGS = 'agentsi.p-1.settings';
const LEGACY_TOKEN = 'agentsi.legacy.p-1.token';
const NEW_TOKEN = 'agentsi.p-1.token';
const FLAG = 'agentsi.migrated.p-1';

function stubScheme(dark: boolean): void {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: 375,
  });
  const matchMedia = (query: string) => ({
    matches: query === '(prefers-color-scheme: dark)' && dark,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: matchMedia,
  });
}

function renderAppAt(path: string): void {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: [path],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale('en');
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe.each([false, true])('r2a migration on the real page (dark=%s)', (dark) => {
  it('copies legacy values, keeps old copies, flags, and reports with existing keys', async () => {
    stubScheme(dark);
    window.localStorage.setItem(LEGACY_SETTINGS, '{"theme":"dark"}');
    window.localStorage.setItem(LEGACY_TOKEN, 'token-abc');
    renderAppAt('/migration');
    expect(await screen.findByText(t('migration.title'))).toBeTruthy();
    expect(screen.getByText(t('migration.keepsOldCopies'))).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText(t('migration.done'))).toBeTruthy();
    });
    expect(window.localStorage.getItem(LEGACY_SETTINGS)).toBe('{"theme":"dark"}');
    expect(window.localStorage.getItem(LEGACY_TOKEN)).toBe('token-abc');
    expect(window.localStorage.getItem(NEW_SETTINGS)).toBe('{"theme":"dark"}');
    expect(window.localStorage.getItem(NEW_TOKEN)).toBe('token-abc');
    expect(window.localStorage.getItem(FLAG)).toBe('true');
  });
});
