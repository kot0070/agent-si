/** @vitest-environment jsdom */
// FXFIRST items 2-5 on the real wizard page: step-3 labels, one-step-own
// controls, team gate with no provider, honest validation, no raw enum in
// user text. Network boundary ONLY (global fetch); FAKE key material only.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { FirstRunFlow } from '../FirstRunFlow';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import { clearUiToken, setUiToken } from '../../../api/errors';
import en from '../../../locale/en.json';
import { ApiClientProvider } from '../../ApiClientProvider';
import { HttpApiClient } from '../../../api/client';
import { MemoryRouter } from 'react-router-dom';

const FX_TOKEN = 'fxfirst-wizard-token';

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

interface FetchOptions {
  connected: string[];
  failProjectsWith?: { status: number; body: unknown };
}

function installFetch(options: FetchOptions): void {
  let projects: Array<{ project_id: string; name: string }> = [];
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
        return ok({ providers: options.connected.map((provider_id) => ({ provider_id })) });
      }
      if (url === '/api/v1/providers/keys/check' && method === 'POST') {
        return ok({});
      }
      if (url === '/api/v1/projects' && method === 'GET') {
        return ok({ projects });
      }
      if (url === '/api/v1/projects' && method === 'POST') {
        if (options.failProjectsWith !== undefined) {
          return ok(options.failProjectsWith.body, options.failProjectsWith.status);
        }
        const payload = body as { name: string };
        const row = { project_id: `p-${projects.length + 1}`, name: payload.name };
        projects.push(row);
        return ok({ project: { ...row, created_at: '2026-01-01T00:00:00Z' } });
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
      if (url === '/api/v1/sidecar/pick-folder' && method === 'POST') {
        return ok({ path: '/fake/picked-folder' });
      }
      if (url.startsWith('/api/v1/tasks') && method === 'POST') {
        const payload = body as { title: string; scope: string[] };
        return ok({
          task: {
            task_id: 't-1',
            project_id: 'p-1',
            title: payload.title,
            status: 'QUEUED',
            created_at: '2026-01-01T00:00:00Z',
          },
        });
      }
      return ok({ code: 'CONTEXT_MISSING' }, 404);
    },
  );
}

function renderWizard(options: FetchOptions, initialStep?: 'connectProvider' | 'oneClickTeam' | 'projectFolder' | 'firstTask'): void {
  installFetch(options);
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <MemoryRouter>
        <FirstRunFlow initialStep={initialStep} onComplete={() => undefined} />
      </MemoryRouter>
    </ApiClientProvider>,
  );
}

function clickNext(): void {
  fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
}

async function skipToFolderStep(): Promise<void> {
  expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
  fireEvent.change(
    screen.getByRole('textbox', { name: en.shell.topbar.project }),
    { target: { value: 'Team Alpha' } },
  );
  fireEvent.click(screen.getByRole('button', { name: en.settings.roleProfile.title }));
  expect(await screen.findByTestId('firstrun-team-result')).toBeTruthy();
  clickNext();
  expect(await screen.findByRole('heading', { name: en.firstrun.steps.projectFolder })).toBeTruthy();
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  setUiToken(FX_TOKEN);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('fxfirst step 3 owns its controls and labels', () => {
  it('labels the project folder with its own keys, never benchmark copy', async () => {
    renderWizard({ connected: [] });
    await skipToFolderStep();
    const folder = screen.getByRole('textbox', { name: en.firstrun.folder.label });
    expect(folder.getAttribute('placeholder')).toBe(en.firstrun.folder.hint);
    expect(screen.queryByText(en.settings.localbench.pathLabel)).toBeNull();
    expect(screen.queryByText(en.settings.localbench.pathHint)).toBeNull();
  });

  it('shows only step-3 controls: project create plus Back, no task or team buttons', async () => {
    renderWizard({ connected: [] });
    await skipToFolderStep();
    expect(
      screen.getByRole('button', { name: en.projects.list.create }),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: en.firstrun.back })).toBeTruthy();
    expect(screen.queryByRole('button', { name: en.tasks.creator.create })).toBeNull();
    expect(
      screen.queryByRole('button', { name: en.firstrun.steps.oneClickTeam }),
    ).toBeNull();
  });

  it('empty folder names the missing folder plainly with no raw enum', async () => {
    renderWizard({ connected: [] });
    await skipToFolderStep();
    fireEvent.click(screen.getByRole('button', { name: en.projects.list.create }));
    const panel = await screen.findByTestId('kit-error-panel');
    const sentence = within(panel).getByText(en.firstrun.folder.required);
    expect(sentence.textContent).not.toContain('CONTEXT_');
    expect(sentence.textContent).not.toContain('VALIDATION_');
    expect((await screen.findByTestId('kit-error-code')).textContent).toBe('VALIDATION_REQUIRED');
    expect(screen.queryByTestId('firstrun-project-result')).toBeNull();
  });
});

describe('fxfirst team gate with no provider', () => {
  it('disables the team button with the reason plus a link to step 1', async () => {
    renderWizard({ connected: [] }, 'oneClickTeam');
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    const button = screen.getByRole('button', { name: en.settings.roleProfile.title });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(await screen.findByTestId('firstrun-team-need-provider')).toBeTruthy();
    expect(screen.getByTestId('firstrun-team-need-provider').textContent).toContain(
      en.firstrun.team.needProvider,
    );
    fireEvent.click(screen.getByTestId('firstrun-team-back'));
    expect(await screen.findByRole('heading', { name: en.firstrun.steps.connectProvider })).toBeTruthy();
  });

  it('empty team name names the missing name plainly with no raw enum', async () => {
    renderWizard({ connected: [] });
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    // Skipped runs keep the enabled button; the empty name still validates.
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
    expect(await screen.findByRole('heading', { name: en.firstrun.steps.oneClickTeam })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.settings.roleProfile.title }));
    const panel = await screen.findByTestId('kit-error-panel');
    expect(within(panel).getByText(en.firstrun.team.nameRequired)).toBeTruthy();
    expect((await screen.findByTestId('kit-error-code')).textContent).toBe('VALIDATION_REQUIRED');
  });

  it('connected provider enables the team and shows the team made', async () => {
    renderWizard({ connected: ['ollama'] }, 'oneClickTeam');
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    await waitFor(() => {
      expect(
        (screen.getByRole('button', { name: en.settings.roleProfile.title }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    expect(screen.queryByTestId('firstrun-team-need-provider')).toBeNull();
    fireEvent.change(
      screen.getByRole('textbox', { name: en.shell.topbar.project }),
      { target: { value: 'Team Alpha' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.settings.roleProfile.title }));
    const result = await screen.findByTestId('firstrun-team-result');
    expect(result.textContent).toContain('Team Alpha');
  });
});

describe('fxfirst first task never leaks a raw enum', () => {
  it('empty title names the missing title plainly', async () => {
    renderWizard({ connected: [] });
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
    clickNext();
    clickNext();
    expect(await screen.findByRole('heading', { name: en.tasks.creator.title })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    const panel = await screen.findByTestId('kit-error-panel');
    expect(within(panel).getByText(en.tasks.creator.titleRequired)).toBeTruthy();
    expect((await screen.findByTestId('kit-error-code')).textContent).toBe('VALIDATION_REQUIRED');
    expect(screen.queryByTestId('firstrun-task-result')).toBeNull();
  });

  it('served plain-detail failure shows a plain sentence with the code behind Details', async () => {
    renderWizard({ connected: [], failProjectsWith: { status: 403, body: { detail: 'forbidden' } } });
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.skip }));
    clickNext();
    clickNext();
    fireEvent.change(
      screen.getByRole('textbox', { name: en.tasks.creator.title }),
      { target: { value: 'My first task' } },
    );
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    const panel = await screen.findByTestId('kit-error-panel');
    const sentence = within(panel).getByText(en.api.error.context_wrong_contract_version);
    expect(sentence.textContent).not.toContain('CONTEXT_WRONG_CONTRACT_VERSION');
    expect((await screen.findByTestId('kit-error-code')).textContent).toBe(
      'CONTEXT_WRONG_CONTRACT_VERSION',
    );
    expect(screen.queryByTestId('firstrun-task-result')).toBeNull();
  });
});
