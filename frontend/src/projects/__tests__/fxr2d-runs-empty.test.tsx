// CRAWL-1: the Runs tab with a project selected must not say
// "No projects yet." — it names the runs empty state.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { FakeApiClient } from '../../api/__tests__/fakeApiClient';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { RunHistory } from '../RunHistory';
import en from '../../locale/en.json';

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

describe('CRAWL-1 runs empty state', () => {
  it('says "No runs yet", never "No projects yet"', async () => {
    const client = new FakeApiClient({
      projects: [{ project_id: 'p-9', name: 'n-9', created_at: '2026-01-01T00:00:00Z' }],
      ledgerByProject: { 'p-9': [] },
      tasksByProject: { 'p-9': [] },
    });
    render(
      <ApiClientProvider client={client}>
        <RunHistory projectId="p-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText('No runs yet.')).toBeTruthy();
    expect(screen.queryByText(en.projects.list.empty)).toBeNull();
  });
});
