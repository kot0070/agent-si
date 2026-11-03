// K10FIRSTRUN served proof: the REAL /firstrun route wired to real actions.
// Mock ONLY at the network boundary (global fetch); no props or client
// doubles are injected into any component under test.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { FirstRunFlow } from '../FirstRunFlow';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import en from '../../../locale/en.json';
import { ApiClientProvider } from '../../ApiClientProvider';
import { HttpApiClient } from '../../../api/client';
import { App } from '../../App';

interface SeenCall {
  url: string;
  method: string;
  body: unknown;
}

let seen: SeenCall[] = [];
let projects: Array<{ project_id: string; name: string; created_at: string }> = [];
let failTasks = false;
const connected = new Set<string>();

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function installFetch(): void {
  seen = [];
  projects = [];
  failTasks = false;
  connected.clear();
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
        return json({ providers: [...connected].map((provider_id) => ({ provider_id })) });
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
        return json({ provider: { provider_id: (body as { preset_id: string }).preset_id } });
      }
      if (url === '/api/v1/projects' && method === 'GET') {
        return json({ projects });
      }
      if (url === '/api/v1/projects' && method === 'POST') {
        const payload = body as { name: string; folder_ref: string };
        const row = {
          project_id: `p-${projects.length + 1}`,
          name: payload.name,
          created_at: '2026-01-01T00:00:00Z',
        };
        projects.push(row);
        return json({ project: row });
      }
      if (url.startsWith('/api/v1/tasks') && method === 'POST') {
        if (failTasks) {
          return json({ code: 'CONTEXT_WRONG_CONTRACT_VERSION' }, 400);
        }
        const payload = body as { title: string; scope: string[] };
        const projectId =
          new URL(url, 'http://localhost').searchParams.get('project_id') ?? 'p-1';
        return json({
          task: {
            task_id: 't-1',
            project_id: projectId,
            title: payload.title,
            status: 'QUEUED',
            created_at: '2026-01-01T00:00:00Z',
          },
        });
      }
      if (url.startsWith('/api/v1/routing/role') && method === 'PUT') {
        const payload = body as { project_id: string; role: string; mode: string };
        return json({
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
      // FXR2E two-step check (416ddaa, merged 0661228): read-only preflight.
      if (url === '/api/v1/providers/keys/check' && method === 'POST') {
        return json({});
      }
      return json({ code: 'CONTEXT_MISSING' }, 404);
    },
  );
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

function clickNext(): void {
  fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('K10FIRSTRUN served first run at the real /firstrun route', () => {
  it('clicks connect->team->folder->firstTask through the real task API', async () => {
    const router = renderFirstrun();
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();

    // connectProvider: the Next gate opens only for a served connection.
    // Connect OpenAI through the real modal with a fake key.
    expect(
      (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement).disabled,
    ).toBe(true);
    const openaiRow = await screen.findByTestId('firstrun-provider-openai');
    fireEvent.click(
      within(openaiRow).getByRole('button', { name: `Connect OpenAI` }),
    );
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(dialog).getByLabelText(en.providers.connect.apiKey),
      { target: { value: 'fx-fake-key' } },
    );
    // FXR2E two-step (416ddaa, merged 0661228): Check before Save.
    fireEvent.click(
      within(dialog).getByRole('button', { name: en.providers.connect.check }),
    );
    await within(dialog).findByText(en.providers.connect.checked);
    fireEvent.click(
      within(dialog).getByRole('button', { name: en.providers.connect.save }),
    );
    await waitFor(() => {
      expect(
        (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    clickNext();

    // oneClickTeam: one click provisions the team project plus role profiles.
    fireEvent.change(
      screen.getByRole('textbox', { name: en.shell.topbar.project }),
      { target: { value: 'Team Alpha' } },
    );
    fireEvent.click(
      screen.getByRole('button', { name: en.settings.roleProfile.title }),
    );
    const teamResult = await screen.findByTestId('firstrun-team-result');
    expect(teamResult.textContent).toContain('p-1');
    const rolePuts = seen.filter(
      (call) => call.url === '/api/v1/routing/role' && call.method === 'PUT',
    );
    expect(rolePuts.length).toBeGreaterThan(0);
    clickNext();

    // projectFolder: the folder input creates the project through the real API.
    fireEvent.change(
      screen.getByRole('textbox', { name: en.firstrun.folder.label }),
      { target: { value: 'alpha-folder' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.projects.list.create }));
    const projectResult = await screen.findByTestId('firstrun-project-result');
    expect(projectResult.textContent).toContain('p-2');
    const projectPosts = seen.filter(
      (call) => call.url === '/api/v1/projects' && call.method === 'POST',
    );
    expect(projectPosts.length).toBe(2);
    clickNext();

    // firstTask: submitting posts through the real task-API submit path.
    fireEvent.change(
      screen.getByRole('textbox', { name: en.tasks.creator.title }),
      { target: { value: 'My first task' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    const taskResult = await screen.findByTestId('firstrun-task-result');
    expect(taskResult.textContent).toContain('My first task');
    const taskPosts = seen.filter(
      (call) => call.url.startsWith('/api/v1/tasks') && call.method === 'POST',
    );
    expect(taskPosts.length).toBe(1);
    expect(taskPosts[0]?.body).toMatchObject({ title: 'My first task', scope: [] });

    // Finished state continues into the app via the route onComplete.
    fireEvent.click(screen.getByRole('button', { name: en.shell.sidebar.chat }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });

  it('foreign route renders no firstrun evidence', async () => {
    const router = createMemoryRouter([{ path: '*', element: <App /> }], {
      initialEntries: ['/about'],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    expect(await screen.findByText('Agent SI')).toBeTruthy();
    expect(screen.queryByText(en.firstrun.title)).toBeNull();
    expect(screen.queryByTestId('firstrun-task-result')).toBeNull();
  });

  it('empty evidence never reaches the finished state', async () => {
    failTasks = true;
    const router = renderFirstrun();
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
    clickNext();
    clickNext();
    fireEvent.change(
      screen.getByRole('textbox', { name: en.tasks.creator.title }),
      { target: { value: 'My first task' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(await screen.findByTestId('kit-error-panel')).toBeTruthy();
    expect(screen.queryByTestId('firstrun-task-result')).toBeNull();
    expect(router.state.location.pathname).toBe('/firstrun');
  });

  it('injected props alone cross no network boundary', () => {
    const fetchSpy = vi.fn(async () => json({}));
    vi.stubGlobal('fetch', fetchSpy);
    let done = false;
    render(<FirstRunFlow onComplete={() => { done = true; }} />);
    clickNext();
    clickNext();
    clickNext();
    fireEvent.change(
      screen.getByRole('textbox', { name: en.tasks.creator.title }),
      { target: { value: 'My first task' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(done).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
