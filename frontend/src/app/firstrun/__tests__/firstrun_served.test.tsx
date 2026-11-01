// K10FIRSTRUN served proof: the REAL /firstrun route wired to real actions.
// Mock ONLY at the network boundary (global fetch); no props or client
// doubles are injected into any component under test.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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

    // connectProvider: the step links to the existing providers settings route.
    const providersLink = screen.getByRole('link', { name: en.settings.models.title });
    expect(providersLink.getAttribute('href')).toBe('/settings/models');
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
      screen.getByRole('textbox', { name: en.settings.localbench.pathLabel }),
      { target: { value: 'alpha-folder' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
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
    expect(router.state.location.pathname).toBe('/');
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
    clickNext();
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
