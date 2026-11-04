/** @vitest-environment jsdom */
// PLANB Z4 (DEFECT-39): Local benchmark on a connected Ollama. The real tab
// runs over the real HTTP client; only fetch (the network boundary) is faked
// with the wire shapes the server really answers: POST runs -> {run_id},
// GET runs/status, GET results.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { LocalBenchTab } from '../LocalBenchTab';
import { HttpLocalBenchClient } from '../LocalBenchClient';
import { resetLocaleForTests, setLocale } from '../../locale/index';

const HARDWARE = {
  gpu_vendor: 'CPU-only',
  gpu_model: null,
  vram_mb: null,
  ram_mb: 16384,
  cpu_only: true,
};
const ROWS = [
  { case_id: 'q01', kind: 'MEASURED', model_id: 'local-a', hardware: HARDWARE, score: 1 },
  { case_id: 'q02', kind: 'MEASURED', model_id: 'local-a', hardware: HARDWARE, score: 0 },
];

type Seen = Array<{ method: string; url: string }>;

function stubServer(states: Array<Record<string, unknown>>, seen: Seen): void {
  let polls = 0;
  vi.stubGlobal('fetch', async (url: unknown, init?: { method?: string }) => {
    const u = String(url);
    seen.push({ method: init?.method ?? 'GET', url: u });
    const json = (body: unknown) =>
      new Response(JSON.stringify(body), { status: 200 });
    if (u.startsWith('/api/v1/local/bench/scan')) {
      return json(['local-a']);
    }
    if (u.startsWith('/api/v1/local/bench/estimate')) {
      return json({ level: 'Quick', model_id: 'local-a', minutes_min: 1, minutes_max: 2 });
    }
    if (u === '/api/v1/local/bench/runs') {
      return json({ run_id: 'run-9' });
    }
    if (u.startsWith('/api/v1/local/bench/runs/status')) {
      const state = states[Math.min(polls, states.length - 1)];
      polls += 1;
      return json({ run_id: 'run-9', done_cases: 0, total_cases: 6, reason: '', ...state });
    }
    if (u.startsWith('/api/v1/local/bench/results')) {
      return json(ROWS);
    }
    if (u === '/api/v1/local/bench/runs/stop') {
      return new Response(null, { status: 200 });
    }
    return new Response('{}', { status: 404 });
  });
}

async function startRun(): Promise<void> {
  render(<LocalBenchTab client={new HttpLocalBenchClient()} />);
  fireEvent.change(screen.getByTestId('localbench-path'), {
    target: { value: 'bench-cases' },
  });
  fireEvent.click(screen.getByTestId('localbench-scan'));
  await screen.findByText('local-a');
  fireEvent.click(screen.getByTestId('localbench-model-local-a'));
  fireEvent.click(screen.getByTestId('localbench-run'));
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('PLANB Z4 local benchmark', () => {
  it('startRun reads the {run_id} object the server answers', async () => {
    stubServer([{ state: 'running' }], []);
    await expect(
      new HttpLocalBenchClient().startRun({ model_id: 'm', level: 'quick' }),
    ).resolves.toBe('run-9');
  });

  it('waits for the run to complete, then shows the measured rows', async () => {
    const seen: Seen = [];
    stubServer([{ state: 'running' }, { state: 'completed', done_cases: 2, total_cases: 2 }], seen);
    await startRun();
    expect(await screen.findByTestId('localbench-result-q01', {}, { timeout: 8000 })).toBeTruthy();
    expect(screen.getByTestId('localbench-result-q02')).toBeTruthy();
    expect(document.body.textContent).not.toContain('Something went wrong');
    expect(seen.filter((s) => s.url.startsWith('/api/v1/local/bench/runs/status')).length).toBeGreaterThanOrEqual(2);
  }, 15000);

  it('an aborted run shows the real reason, not the generic error, and frees the run', async () => {
    const seen: Seen = [];
    const reason = 'bench chat refused: loopback runtime unreachable (timed out) (case q01)';
    stubServer([{ state: 'aborted', reason }], seen);
    await startRun();
    const line = await screen.findByTestId('localbench-run-error', {}, { timeout: 8000 });
    expect(line.textContent).toContain(reason);
    expect(document.body.textContent).not.toContain('Something went wrong');
    await waitFor(() =>
      expect(seen).toContainEqual({ method: 'POST', url: '/api/v1/local/bench/runs/stop' }),
    );
  }, 15000);
});
