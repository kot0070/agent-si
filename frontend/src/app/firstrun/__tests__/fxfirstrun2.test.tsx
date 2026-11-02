// FXFIRSTRUN2 RED: focused first-run page. Network boundary ONLY (global
// fetch); no props/client doubles. FAKE key material only.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
// @ts-ignore: node types unavailable offline
import { readFileSync } from 'node:fs';
import { FirstRunFlow } from '../FirstRunFlow';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import { getUiToken, setUiToken, clearUiToken } from '../../../api/errors';
import en from '../../../locale/en.json';
import uk from '../../../locale/uk.json';
import { ApiClientProvider } from '../../ApiClientProvider';
import { HttpApiClient } from '../../../api/client';
import { App } from '../../App';

const FX_KEY = 'fx-fake-key-value';
const FX_TOKEN = 'fx-ui-token-02';

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

interface SeenCall {
  url: string;
  method: string;
  body: unknown;
}

function installFetch(): { seen: SeenCall[]; connected: Set<string> } {
  const seen: SeenCall[] = [];
  const connected = new Set<string>();
  let projects: Array<{ project_id: string; name: string; created_at: string }> = [];
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
      seen.push({ url, method, body });
      if (url === '/api/v1/providers' && method === 'GET') {
        return ok({ providers: [...connected].map((provider_id) => ({ provider_id })) });
      }
      if (url === '/api/v1/providers/keys' && method === 'POST') {
        const preset = (body as { preset_id: string }).preset_id;
        return new Response(
          JSON.stringify({ key_ref: { secret_id: preset, provider_id: preset } }),
          { status: 201, headers: { 'content-type': 'application/json' } },
        );
      }
      if (url === '/api/v1/providers/connect' && method === 'POST') {
        connected.add((body as { preset_id: string }).preset_id);
        return ok({ provider: { provider_id: (body as { preset_id: string }).preset_id } });
      }
      if (url === '/api/v1/local/connect' && method === 'POST') {
        connected.add('ollama');
        return ok({ connected: true });
      }
      if (url === '/api/v1/projects' && method === 'GET') {
        return ok({ projects });
      }
      if (url === '/api/v1/projects' && method === 'POST') {
        const payload = body as { name: string; folder_ref: string };
        const row = { project_id: `p-${projects.length + 1}`, name: payload.name, created_at: '2026-01-01T00:00:00Z' };
        projects.push(row);
        return ok({ project: row });
      }
      if (url === '/api/v1/sidecar/pick-folder' && method === 'POST') {
        return ok({ path: '/fake/picked-folder' });
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
      if (url.startsWith('/api/v1/tasks') && method === 'POST') {
        const payload = body as { title: string; scope: string[] };
        const projectId =
          new URL(url, 'http://localhost').searchParams.get('project_id') ?? 'p-1';
        return ok({
          task: {
            task_id: 't-1',
            project_id: projectId,
            title: payload.title,
            status: 'QUEUED',
            created_at: '2026-01-01T00:00:00Z',
          },
        });
      }
      if (url.startsWith('/api/v1/tasks') && method === 'GET') {
        return ok({ tasks: [] });
      }
      return new Response(JSON.stringify({ code: 'CONTEXT_MISSING' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      });
    },
  );
  return { seen, connected };
}

function renderFirstrun(): ReturnType<typeof createMemoryRouter> {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: ['/firstrun'],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
  return router;
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

describe('FXFIRSTRUN2 focused first-run page', () => {
  it('step 1 shows provider rows with Connect; Next gates on served connection', async () => {
    installFetch();
    renderFirstrun();
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    for (const name of ['Meta', 'OpenAI', 'Anthropic', 'Ollama']) {
      const row = await screen.findByTestId(`firstrun-provider-${name.toLowerCase()}`);
      expect(within(row).getByText(name)).toBeTruthy();
      expect(
        within(row).getByRole('button', { name: `Connect ${name}` }),
      ).toBeTruthy();
    }
    const next = screen.getByRole('button', { name: en.firstrun.next });
    expect((next as HTMLButtonElement).disabled).toBe(true);
  });

  it('Connect opens the real modal; a FAKE-key save connects and enables Next', async () => {
    installFetch();
    renderFirstrun();
    await screen.findByText(en.firstrun.title);
    const row = await screen.findByTestId('firstrun-provider-openai');
    fireEvent.click(within(row).getByRole('button', { name: 'Connect OpenAI' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(en.providers.connect.apiKey), {
      target: { value: FX_KEY },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: en.providers.connect.save }));
    await waitFor(() => {
      expect(
        within(screen.getByTestId('firstrun-provider-openai')).getByText(
          en.providers.connect.connected.replace('{label}', 'OpenAI'),
        ),
      ).toBeTruthy();
    });
    await waitFor(() => {
      expect(
        (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
  });

  it('Skip for now advances without marking anything done', async () => {
    installFetch();
    renderFirstrun();
    await screen.findByText(en.firstrun.title);
    expect(
      (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
    expect(await screen.findByRole('heading', { name: en.firstrun.steps.oneClickTeam })).toBeTruthy();
    expect(window.localStorage.getItem('agentsi.firstrun.done')).not.toBe('true');
  });

  it('one click creates the team and shows who was set; folder picker is real; first message lands in Chat', async () => {
    const { seen } = installFetch();
    const router = renderFirstrun();
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));

    fireEvent.change(
      screen.getByRole('textbox', { name: en.shell.topbar.project }),
      { target: { value: 'Team Alpha' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: en.settings.roleProfile.title }),
    );
    const teamResult = await screen.findByTestId('firstrun-team-result');
    expect(teamResult.textContent).toContain('Team Alpha');
    for (const role of Object.values(en.providers.role)) {
      expect(teamResult.textContent).toContain(role);
    }
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));

    fireEvent.click(screen.getByTestId('firstrun-folder-choose'));
    await waitFor(() => {
      expect(
        (screen.getByRole('textbox', { name: en.settings.localbench.pathLabel }) as HTMLInputElement).value,
      ).toBe('/fake/picked-folder');
    });
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect((await screen.findByTestId('firstrun-project-result')).textContent).toContain('p-');
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));

    expect(screen.queryByRole('button', { name: en.firstrun.next })).toBeNull();
    fireEvent.change(
      screen.getByRole('textbox', { name: en.tasks.creator.title }),
      { target: { value: 'My first run' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect((await screen.findByTestId('firstrun-task-result')).textContent).toContain(
      'My first run',
    );
    const taskPosts = seen.filter(
      (call) => call.url.startsWith('/api/v1/tasks') && call.method === 'POST',
    );
    expect(taskPosts).toHaveLength(1);
    expect(taskPosts[0]?.body).toMatchObject({ title: 'My first run', scope: [] });
    fireEvent.click(screen.getByRole('button', { name: en.shell.sidebar.chat }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });

  it('optional steps are one quiet list on the last step only', async () => {
    installFetch();
    renderFirstrun();
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    expect(screen.queryByText(en.firstrun.optionalNote)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(await screen.findByText(en.firstrun.optionalNote)).toBeTruthy();
    const card = screen.getByTestId('firstrun');
    for (const title of Object.values(en.firstrun.optional)) {
      expect(within(card).getByText(title)).toBeTruthy();
    }
    const quiet = screen.getAllByRole('button', { name: en.firstrun.skip });
    expect(quiet).toHaveLength(4);
    for (const button of quiet) {
      expect(button.classList.contains('fx-btn-quiet')).toBe(true);
    }
  });

  it('uk locale walks the focused flow', async () => {
    setLocale('uk');
    installFetch();
    renderFirstrun();
    expect(await screen.findByText(uk.firstrun.title)).toBeTruthy();
    for (const name of ['Meta', 'OpenAI', 'Anthropic', 'Ollama']) {
      expect(await screen.findByTestId(`firstrun-provider-${name.toLowerCase()}`)).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('button', { name: uk.firstrun.skip }));
    expect(await screen.findByRole('heading', { name: uk.firstrun.steps.oneClickTeam })).toBeTruthy();
  });

  it('firstrun.css scopes a 640 focused card and hides the right panel plus project list', () => {
    const css = readFileSync('src/app/firstrun/firstrun.css', 'utf8');
    expect(css).toContain('640px');
    expect(css).toContain('section[data-testid="firstrun"]');
    expect(css).toContain(':has(section[data-testid="firstrun"])');
    expect(css).toContain('aside[data-testid="inspector"]');
    expect(css).toContain('.fx-project-list');
    expect(css).toContain('p[data-testid="firstrun-gate-links"]');
  });
});
