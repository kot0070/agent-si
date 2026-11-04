// H6 RED: the results card shows the run record's folder path plus its
// produced file names, with an Open folder button where the sidecar
// can open it.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import type { ReactElement } from 'react';
import { HttpApiClient } from '../../api/client';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { Inspector } from '../Inspector';

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const FOLDER = 'C:\\runs\\p1';
const RUNS_LEDGER = {
  rows: [{ package_id: 'pkg-1', agents: 1, peak_concurrency: 1, wall_time_s: 10 }],
  runs: [
    {
      run_id: 'run-1',
      project: 'p-1',
      task: 'say hi',
      folder: FOLDER,
      start: '2026-02-11T06:40:00Z',
      end: '2026-02-11T06:42:44Z',
      success: true,
      stopped: false,
      summary: 'did it',
      parts: [],
      verdicts: {},
      tokens: 10,
      cost: 'UNKNOWN',
      files: ['hello.txt'],
    },
  ],
};

const seenOpens: unknown[] = [];
let openStatus = 200;

function stub(openOk: boolean): void {
  openStatus = openOk ? 200 : 409;
  vi.stubGlobal(
    'fetch',
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'GET' && url.startsWith('/api/v1/runs/ledger')) {
        return jsonBody(RUNS_LEDGER);
      }
      if (method === 'GET' && url === '/api/v1/projects') {
        return jsonBody({ projects: [] });
      }
      if (method === 'POST' && url === '/api/v1/sidecar/open-folder') {
        let body: unknown = null;
        try {
          body = JSON.parse(String(init?.body ?? 'null'));
        } catch {
          body = null;
        }
        seenOpens.push(body);
        if (openStatus !== 200) {
          return jsonBody({ code: 'NATIVE_OPEN_UNAVAILABLE' }, 409);
        }
        return jsonBody({ ok: true, path: FOLDER });
      }
      if (method === 'GET') {
        return jsonBody({ code: 'FXR2D_UNEXPECTED_API' }, 404);
      }
      return jsonBody({ code: 'FXR2D_UNEXPECTED_API' }, 404);
    },
  );
}

function InspectorShell(): ReactElement {
  return <Inspector projectId="p-1" live={<span>live</span>} />;
}

function renderInspector(): void {
  const router = createMemoryRouter([{ path: '*', element: <InspectorShell /> }], {
    initialEntries: ['/'],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem('agentsi.locale', 'en');
  setLocale('en');
  seenOpens.length = 0;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('H6 results card folder', () => {
  it('shows the run folder path plus produced files and opens it', async () => {
    stub(true);
    renderInspector();
    // FXFACTS F10: Results renders closed; open it first.
    fireEvent.click(await screen.findByTestId('rail-toggle-results'));
    const folder = await screen.findByTestId('result-last-folder');
    expect(folder.textContent).toContain('runs');
    expect(folder.getAttribute('title')).toBe(FOLDER);
    expect(await screen.findByTestId('result-file-0')).toBeTruthy();
    const open = await screen.findByTestId('result-open-folder');
    fireEvent.click(open);
    await screen.findByTestId('result-last-folder');
    expect(seenOpens).toEqual([{ path: FOLDER }]);
  });

  it('hides the Open folder button where the sidecar cannot open', async () => {
    stub(false);
    renderInspector();
    // FXFACTS F10: Results renders closed; open it first.
    fireEvent.click(await screen.findByTestId('rail-toggle-results'));
    const open = await screen.findByTestId('result-open-folder');
    fireEvent.click(open);
    await waitFor(() => {
      expect(screen.queryByTestId('result-open-folder')).toBeNull();
    });
  });
});
