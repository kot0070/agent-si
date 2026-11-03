// U9: the settings hub reaches /about and /how-it-works; the hub link
// wears the page label, never a stray run title.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApiClientProvider } from '../ApiClientProvider';
import { HttpApiClient } from '../../api/client';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { App } from '../App';
import en from '../../locale/en.json';

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function installFetch(): void {
  vi.stubGlobal(
    'fetch',
    async (input: unknown) => {
      const url = String(input);
      if (url === '/api/v1/providers' || url.startsWith('/api/v1/providers/')) {
        return json({ providers: [] });
      }
      if (url === '/api/v1/agents/live') {
        return json({ agents: [] });
      }
      if (url === '/api/v1/projects') {
        return json({ projects: [] });
      }
      return json({ code: 'CONTEXT_MISSING' }, 404);
    },
  );
}

function renderApp(route: string): void {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  installFetch();
  window.localStorage.setItem('agentsi.firstrun.done', 'true');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('U9 settings hub reaches the info pages', () => {
  it('hub shows About and How-it-works links with page labels', async () => {
    renderApp('/settings');
    const about = await screen.findByTestId('settings-about');
    expect(about.getAttribute('href')).toBe('/about');
    expect(about.textContent).toContain(en.settings.hub.about);
    const how = await screen.findByTestId('settings-how-it-works');
    expect(how.getAttribute('href')).toBe('/how-it-works');
    expect(how.textContent).toContain(en.settings.hub.howItWorks);
    expect(how.textContent).not.toContain(en.howItWorks.runs.title);
  });

  it('the About hub link opens the licence page', async () => {
    renderApp('/settings');
    fireEvent.click(await screen.findByTestId('settings-about'));
    expect(await screen.findByText('Agent SI')).toBeTruthy();
    expect(await screen.findByText(en.about.licence.line)).toBeTruthy();
  });
});
