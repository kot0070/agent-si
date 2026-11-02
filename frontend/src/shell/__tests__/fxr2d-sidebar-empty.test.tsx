// CRAWL-8: with 0 projects the rail names the empty state instead of
// spinning "Loading more"; a first load that never settles becomes a
// retryable failure, never an endless loader.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { FakeApiClient } from '../../api/__tests__/fakeApiClient';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { Sidebar } from '../Sidebar';
import en from '../../locale/en.json';

class HangingClient extends FakeApiClient {
  override listProjects(): Promise<never> {
    return new Promise<never>(() => {});
  }
}

function renderSidebar(client: FakeApiClient): void {
  const router = createMemoryRouter([{ path: '/', element: <Sidebar projectId={null} /> }], {
    initialEntries: ['/'],
  });
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('CRAWL-8 rail empty state', () => {
  it('empty store names the empty state, no loader', async () => {
    renderSidebar(new FakeApiClient({ projects: [] }));
    expect(await screen.findByTestId('sidebar-projects-empty')).toBeTruthy();
    expect(screen.getByTestId('sidebar-projects-empty').textContent).toContain(
      en.projects.list.empty,
    );
    expect(screen.queryByTestId('kit-loading-state')).toBeNull();
  });

  it('a hanging first load becomes a retryable failure', async () => {
    vi.useFakeTimers();
    renderSidebar(new HangingClient({ projects: [] }));
    expect(screen.getByTestId('kit-loading-state')).toBeTruthy();
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(screen.queryByTestId('kit-loading-state')).toBeNull();
    expect(screen.getByTestId('kit-error-panel')).toBeTruthy();
    expect(screen.getByTestId('kit-error-retry')).toBeTruthy();
  });
});
