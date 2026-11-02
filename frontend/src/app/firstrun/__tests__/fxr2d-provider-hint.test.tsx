// U14 RED: first-run "Connect a provider" step. Per provider one useful
// line (cloud: API key; Ollama: local, no key); the team/model line lives
// once on the team step instead of under every provider.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { FirstRunFlow } from '../FirstRunFlow';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import { getUiToken, setUiToken, clearUiToken } from '../../../api/errors';
import en from '../../../locale/en.json';
import { ApiClientProvider } from '../../ApiClientProvider';
import { HttpApiClient } from '../../../api/client';
import { App } from '../../App';

const FX_TOKEN = 'fx-ui-token-u14';

const CONNECT_KEY_LINES: Record<string, string> = {
  meta: 'Get a key from your Meta account.',
  openai: 'Get a key from your OpenAI account.',
  anthropic: 'Get a key from your Anthropic account.',
};
const LOCAL_LINE = 'Runs on this PC, no key';
const TEAM_LINE = 'Choose a model per role, or leave a role on Automatic.';

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function installFetch(): void {
  const connected = new Set<string>();
  vi.stubGlobal(
    'fetch',
    async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      let body: unknown = null;
      try {
        body = init?.body === undefined ? null : JSON.parse(init.body);
      } catch {
        body = null;
      }
      if (url === '/api/v1/providers' && method === 'GET') {
        return ok({ providers: [...connected].map((provider_id) => ({ provider_id })) });
      }
      if (url === '/api/v1/providers/keys' && method === 'POST') {
        const preset = (body as { preset_id: string }).preset_id;
        return ok({ key_ref: { secret_id: preset, provider_id: preset } }, 201);
      }
      if (url === '/api/v1/providers/connect' && method === 'POST') {
        connected.add((body as { preset_id: string }).preset_id);
        return ok({ provider: { provider_id: (body as { preset_id: string }).preset_id } });
      }
      if (url === '/api/v1/projects' && method === 'GET') {
        return ok({ projects: [] });
      }
      if (url.startsWith('/api/v1/routing/role') && method === 'PUT') {
        const payload = body as { project_id: string; role: string; mode: string };
        return ok({
          ok: true,
          profile: {
            role: payload.role,
            project_id: payload.project_id,
            mode: payload.mode,
            provider: null,
            model: null,
          },
        });
      }
      return new Response(JSON.stringify({ code: 'CONTEXT_MISSING' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      });
    },
  );
}

function renderFirstrun(): void {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: ['/firstrun'],
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
  setUiToken(FX_TOKEN);
  expect(getUiToken()).toBe(FX_TOKEN);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('U14 provider rows name the connect action', () => {
  it('cloud rows say API key, ollama says local, team line not repeated', async () => {
    installFetch();
    renderFirstrun();
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    for (const id of ['meta', 'openai', 'anthropic']) {
      const row = await screen.findByTestId(`firstrun-provider-${id}`);
      expect(within(row).getByText(CONNECT_KEY_LINES[id] as string)).toBeTruthy();
      expect(within(row).queryByText(TEAM_LINE)).toBeNull();
    }
    const ollama = await screen.findByTestId('firstrun-provider-ollama');
    expect(within(ollama).getByText(LOCAL_LINE)).toBeTruthy();
    expect(within(ollama).queryByText(TEAM_LINE)).toBeNull();
    expect(screen.queryByText(TEAM_LINE)).toBeNull();
  });

  it('team step carries the model-per-role line once', async () => {
    installFetch();
    renderFirstrun();
    await screen.findByText(en.firstrun.title);
    const row = await screen.findByTestId('firstrun-provider-openai');
    fireEvent.click(within(row).getByRole('button', { name: 'Connect OpenAI' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(en.providers.connect.apiKey), {
      target: { value: 'fx-fake-key' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: en.providers.connect.save }));
    await waitFor(() => {
      expect(
        (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement).disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    const hints = await screen.findAllByText(TEAM_LINE);
    expect(hints).toHaveLength(1);
    expect(await screen.findByTestId('firstrun-team-mode-hint')).toBeTruthy();
  });
});
