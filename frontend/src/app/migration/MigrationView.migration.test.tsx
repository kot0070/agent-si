/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MigrationView, runMigration } from './MigrationView';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import en from '../../locale/en.json';

const PROJECT_ID = 'project-1';
const LEGACY_SETTINGS = 'agentsi.legacy.project-1.settings';
const NEW_SETTINGS = 'agentsi.project-1.settings';
const LEGACY_TOKEN = 'agentsi.legacy.project-1.token';
const NEW_TOKEN = 'agentsi.project-1.token';

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

describe('first-start migration keeps old copies', () => {
  it('copies each legacy value to its new key and keeps the legacy entry', async () => {
    window.localStorage.setItem(LEGACY_SETTINGS, '{"theme":"dark"}');
    window.localStorage.setItem(LEGACY_TOKEN, 'token-abc');
    const result = await runMigration(PROJECT_ID);
    expect(result).toEqual({ migrated: true, oldCopiesKept: true });
    expect(window.localStorage.getItem(LEGACY_SETTINGS)).toBe('{"theme":"dark"}');
    expect(window.localStorage.getItem(LEGACY_TOKEN)).toBe('token-abc');
    expect(window.localStorage.getItem(NEW_SETTINGS)).toBe('{"theme":"dark"}');
    expect(window.localStorage.getItem(NEW_TOKEN)).toBe('token-abc');
    expect(window.localStorage.getItem('agentsi.migrated.project-1')).toBe('true');
  });

  it('sets the flag and returns the same shape with no legacy entries, idempotent on rerun', async () => {
    const first = await runMigration(PROJECT_ID);
    expect(first).toEqual({ migrated: true, oldCopiesKept: true });
    expect(window.localStorage.getItem('agentsi.migrated.project-1')).toBe('true');
    const second = await runMigration(PROJECT_ID);
    expect(second).toEqual({ migrated: true, oldCopiesKept: true });
    expect(window.localStorage.getItem('agentsi.migrated.project-1')).toBe('true');
  });

  it('renders the real view and reports the kept-copies outcome', async () => {
    window.localStorage.setItem(LEGACY_SETTINGS, '{"theme":"dark"}');
    render(<MigrationView projectId={PROJECT_ID} />);
    expect(screen.getByText(en.migration.keepsOldCopies)).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText(en.migration.done)).toBeTruthy();
    });
    expect(window.localStorage.getItem(LEGACY_SETTINGS)).toBe('{"theme":"dark"}');
    expect(window.localStorage.getItem(NEW_SETTINGS)).toBe('{"theme":"dark"}');
  });
});
