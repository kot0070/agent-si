// FXROLEPICK R6 (+R4, +R9): the settings index is a grouped list
// (icon, title, purpose, state right, chevron; quiet links; existing
// settings-link-* testids). Every section holds its content plus a
// Back to Settings link (Diagnostics included). The need-it-now block
// shows only on Models and Routing. General carries language, setup
// reset and the where-text. Help rows reach how-it-works/about/migration.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
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
        return json({ providers: [{ provider_id: 'meta' }] });
      }
      if (url === '/api/v1/local/models') {
        return json([]);
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

describe('R6 grouped settings index', () => {
  it('groups sections with icon, title, purpose and a state at the right', async () => {
    renderApp('/settings');
    for (const path of ['models', 'routing', 'localAI', 'capabilityDB', 'optimization', 'project', 'general', 'appearance', 'diagnostics', 'localbench']) {
      expect(await screen.findByTestId(`settings-link-${path}`)).toBeTruthy();
    }
    expect(await screen.findByText('Models and providers')).toBeTruthy();
    expect(await screen.findByText('Limits')).toBeTruthy();
    expect(await screen.findByText('App')).toBeTruthy();
    expect(await screen.findByText('Measure')).toBeTruthy();
    expect(await screen.findByText('Help')).toBeTruthy();
    const modelsRow = await screen.findByTestId('settings-link-models');
    expect(modelsRow.textContent).toContain('1 connected');
    const back = screen.queryByTestId('settings-back');
    expect(back).toBeNull();
  });

  it('Help rows reach how-it-works, about and migration', async () => {
    renderApp('/settings');
    expect((await screen.findByTestId('settings-how-it-works')).getAttribute('href')).toBe('/how-it-works');
    expect((await screen.findByTestId('settings-about')).getAttribute('href')).toBe('/about');
    expect((await screen.findByTestId('settings-migration')).getAttribute('href')).toBe('/migration');
  });

  it('diagnostics holds its content plus a Back link, and models keeps need-it-now', async () => {
    renderApp('/settings/diagnostics');
    expect((await screen.findAllByText('Diagnostics')).length).toBeGreaterThanOrEqual(1);
    const back = await screen.findByTestId('settings-back');
    expect(back.getAttribute('href')).toBe('/settings');
    expect(screen.queryByText(en.diagnostics.needItNow)).toBeNull();
    cleanup();
    renderApp('/settings/models');
    expect(await screen.findByText(en.settings.models.needItNow)).toBeTruthy();
    expect(await screen.findByTestId('settings-back')).toBeTruthy();
  });

  it('need-it-now shows only on Models and Routing', async () => {
    renderApp('/settings/routing');
    expect(await screen.findByText(en.settings.routing.needItNow)).toBeTruthy();
    cleanup();
    renderApp('/settings/general');
    expect((await screen.findAllByText('General')).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(en.settings.general.needItNow)).toBeNull();
  });

  it('general carries language, the setup reset and the where-text', async () => {
    renderApp('/settings/general');
    expect(await screen.findByTestId('settings-general-lang-en')).toBeTruthy();
    expect(await screen.findByTestId('settings-general-lang-uk')).toBeTruthy();
    fireEvent.click(await screen.findByTestId('settings-general-lang-uk'));
    expect(await screen.findByTestId('settings-general-lang-current')).toBeTruthy();
    expect(screen.getByText(en.settings.general.whereText)).toBeTruthy();
    expect(await screen.findByTestId('settings-general-reset')).toBeTruthy();
  });
});
