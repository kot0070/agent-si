// CODER-1 Holt FXFOLDER UI tests (RED-first): the folder-picker lane on
// the real App routes. Mocks only at the network boundary (global fetch):
// ProjectsPage shows a Choose control that POSTs the sidecar pick-folder
// route and fills the folder input, cancel keeps the typed value, a 409
// hides the control while the input stays drivable, and a refused folder
// shows a clear message with no new project row; the first-run folder
// step fills its input from the same route.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { resetLocaleForTests, setLocale } from '../locale/index';
import en from '../locale/en.json';
import { ApiClientProvider } from '../app/ApiClientProvider';
import { HttpApiClient } from '../api/client';
import { App } from '../app/App';

interface SeenCall {
  url: string;
  method: string;
  body: unknown;
}

interface MockProject {
  project_id: string;
  name: string;
  created_at: string;
}

type PickMode = 'choose' | 'cancel' | 'unavailable';

let seen: SeenCall[] = [];
let projects: MockProject[] = [];
let pickMode: PickMode = 'choose';
let pickCalls = 0;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function installFetch(): void {
  seen = [];
  projects = [];
  pickMode = 'choose';
  pickCalls = 0;
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
      if (url === '/api/v1/sidecar/pick-folder' && method === 'POST') {
        pickCalls += 1;
        if (pickMode === 'unavailable') {
          return json(
            {
              code: 'NATIVE_DIALOG_UNAVAILABLE',
              message: 'native folder dialog is unavailable: no window',
            },
            409,
          );
        }
        if (pickMode === 'cancel') {
          return json({ path: null });
        }
        return json({ path: '/chosen/dir' });
      }
      if (url === '/api/v1/providers' && method === 'GET') {
        return json({ providers: [{ provider_id: 'openai' }] });
      }
      if (url === '/api/v1/projects' && method === 'GET') {
        return json({ projects });
      }
      if (url === '/api/v1/projects' && method === 'POST') {
        const payload = body as { name: string; folder_ref: string };
        if (
          typeof payload.folder_ref === 'string' &&
          payload.folder_ref.startsWith('/nonexistent')
        ) {
          return json({ code: 'CONTEXT_MISSING' }, 400);
        }
        const row = {
          project_id: `p-${projects.length + 1}`,
          name: payload.name,
          created_at: '2026-01-01T00:00:00Z',
        };
        projects.push(row);
        return json({ project: row });
      }
      if (url === '/api/v1/routing/role' && method === 'PUT') {
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

function renderAt(path: string): void {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: [path],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function folderInput(): HTMLInputElement {
  return screen.getByTestId('project-add-folder') as HTMLInputElement;
}

function lastProjectPost(): SeenCall | undefined {
  const posts = seen.filter(
    (call) => call.url === '/api/v1/projects' && call.method === 'POST',
  );
  return posts[posts.length - 1];
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

describe('FXFOLDER folder picker on the projects page', () => {
  it('choose fills the folder input and submit posts the typed path exactly', async () => {
    renderAt('/projects');
    await screen.findByTestId('project-add-form');
    fireEvent.click(screen.getByRole('button', { name: 'Choose folder' }));
    const filled = await screen.findByDisplayValue('/chosen/dir');
    expect(pickCalls).toBe(1);
    fireEvent.change(filled, { target: { value: '/typed/path' } });
    expect((filled as HTMLInputElement).value).toBe('/typed/path');
    fireEvent.change(screen.getByTestId('project-add-name'), {
      target: { value: 'Harbor' },
    });
    fireEvent.click(screen.getByTestId('project-add-submit'));
    await waitFor(() => {
      expect(lastProjectPost()?.body).toMatchObject({
        name: 'Harbor',
        folder_ref: '/typed/path',
      });
    });
  });

  it('choose cancel keeps the typed folder', async () => {
    pickMode = 'cancel';
    renderAt('/projects');
    await screen.findByTestId('project-add-form');
    const input = folderInput();
    fireEvent.change(input, { target: { value: '/keep/me' } });
    fireEvent.click(screen.getByRole('button', { name: 'Choose folder' }));
    await waitFor(() => {
      expect(pickCalls).toBe(1);
    });
    expect(input.value).toBe('/keep/me');
  });

  it('choose 409 hides the control while the input stays drivable', async () => {
    pickMode = 'unavailable';
    renderAt('/projects');
    await screen.findByTestId('project-add-form');
    expect(
      screen.getByRole('button', { name: 'Choose folder' }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Choose folder' }));
    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: 'Choose folder' }),
      ).toBeNull();
    });
    const input = folderInput();
    fireEvent.change(input, { target: { value: '/still/typed' } });
    expect(input.value).toBe('/still/typed');
  });

  it('a refused folder shows a clear message and creates no project row', async () => {
    renderAt('/projects');
    await screen.findByTestId('project-add-form');
    expect(
      screen.getByRole('button', { name: 'Choose folder' }),
    ).toBeTruthy();
    fireEvent.change(screen.getByTestId('project-add-name'), {
      target: { value: 'Ghost' },
    });
    fireEvent.change(folderInput(), {
      target: { value: '/nonexistent/row' },
    });
    fireEvent.click(screen.getByTestId('project-add-submit'));
    const panel = await screen.findByTestId('kit-error-panel');
    expect(panel.textContent).toContain(en.api.error.context_missing);
    expect(projects.length).toBe(0);
    expect(screen.queryByText('Ghost')).toBeNull();
  });
});

describe('FXFOLDER folder picker on the first-run folder step', () => {
  it('choose fills the folder input and submit posts it exactly', async () => {
    renderAt('/firstrun');
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    await waitFor(() => {
      expect(
        (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    const input = (await screen.findByRole('textbox', {
      name: en.firstrun.folder.label,
    })) as HTMLInputElement;
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.folder.choose }));
    await waitFor(() => {
      expect(input.value).toBe('/chosen/dir');
    });
    fireEvent.change(input, { target: { value: 'typed-folder' } });
    fireEvent.click(
      screen.getByRole('button', { name: en.projects.list.create }),
    );
    const result = await screen.findByTestId('firstrun-project-result');
    expect(result.textContent).toContain('p-');
    expect(lastProjectPost()?.body).toMatchObject({
      name: 'typed-folder',
      folder_ref: 'typed-folder',
    });
  });

  it('choose 409 hides the control on the folder step', async () => {
    pickMode = 'unavailable';
    renderAt('/firstrun');
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    await waitFor(() => {
      expect(
        (screen.getByRole('button', { name: en.firstrun.next }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    await screen.findByRole('textbox', {
      name: en.firstrun.folder.label,
    });
    expect(
      screen.getByRole('button', { name: en.firstrun.folder.choose }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.folder.choose }));
    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: en.firstrun.folder.choose }),
      ).toBeNull();
    });
  });
});
