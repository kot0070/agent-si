/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { SETTINGS_ROUTES } from '../index';
import { SettingsLayout } from '../../shell/SettingsLayout';
import { LocalBenchTab } from '../LocalBenchTab';
import { HttpLocalBenchClient } from '../LocalBenchClient';
import type { LocalBenchClient } from '../LocalBenchClient';
import {
  LOCALBENCH_ENDPOINTS,
  expandBenchEstimate,
  expandBenchResults,
  expandBenchScan,
  toWireRunBody,
} from '../LocalBenchTypes';
import type {
  BenchmarkLevel,
  LocalBenchEstimate,
  LocalBenchResultRow,
} from '../LocalBenchTypes';
import { resetLocaleForTests, setLocale, t } from '../../locale/index';
import en from '../../locale/en.json';
import uk from '../../locale/uk.json';

type LocaleTable = { settings: { localbench: Record<string, string> } };
const EN_LOCALBENCH: Record<string, string> = (en as unknown as LocaleTable)
  .settings.localbench;
const UK_LOCALBENCH: Record<string, string> = (uk as unknown as LocaleTable)
  .settings.localbench;
const NEW_KEYS = Object.keys(EN_LOCALBENCH).map(
  (leaf) => `settings.localbench.${leaf}`,
);

// FAKE-OF: GET /api/v1/local/bench/scan (M3 scan_route returns model ids).
const SCAN_IDS = ['local-a', 'local-b'];

// FAKE-OF: GET /api/v1/local/bench/estimate (M3 BenchEstimate per level).
function fakeEstimate(modelId: string, level: BenchmarkLevel): LocalBenchEstimate {
  switch (level) {
    case 'quick':
      return { model_id: modelId, level, minutes_min: 1, minutes_max: 2 };
    case 'standard':
      return { model_id: modelId, level, minutes_min: 30, minutes_max: 40 };
    case 'deep':
      return { model_id: modelId, level, minutes_min: 10, minutes_max: 15 };
  }
}

// FAKE-OF: POST /api/v1/local/bench/runs (M3 runs_route returns a run id).
const RUN_ID = 'run-1';

// FAKE-OF: GET /api/v1/local/bench/results (M3 BenchResultRow list).
const RESULT_ROWS: Array<LocalBenchResultRow> = [
  {
    case_id: 'q01',
    kind: 'MEASURED',
    model_id: 'local-a',
    hardware: {
      gpu_vendor: 'CPU-only',
      gpu_model: null,
      vram_mb: null,
      ram_mb: 16384,
      cpu_only: true,
    },
  },
  {
    case_id: 'q02',
    kind: 'PROXY',
    model_id: 'local-b',
    hardware: {
      gpu_vendor: 'CPU-only',
      gpu_model: null,
      vram_mb: null,
      ram_mb: 16384,
      cpu_only: true,
    },
  },
];

function makeFakeClient(): LocalBenchClient {
  return {
    // FAKE-OF: GET /api/v1/local/bench/scan (M3 scan_route ids fixture).
    scanModels: (path: string) =>
      Promise.resolve({
        path,
        models: SCAN_IDS.map((model_id) => ({
          model_id,
          display_name: model_id,
          evidence: 'UNKNOWN' as const,
        })),
      }),
    // FAKE-OF: GET /api/v1/local/bench/estimate (M3 BenchEstimate fixture).
    readEstimate: (modelId: string, level: BenchmarkLevel) =>
      Promise.resolve(fakeEstimate(modelId, level)),
    // FAKE-OF: POST /api/v1/local/bench/runs (M3 runs_route fixture).
    startRun: () => Promise.resolve(RUN_ID),
    // FAKE-OF: POST /api/v1/local/bench/runs/pause (M3 pause_route fixture).
    pauseRun: () => Promise.resolve(),
    // FAKE-OF: POST /api/v1/local/bench/runs/resume (M3 resume_route fixture).
    resumeRun: () => Promise.resolve(),
    // FAKE-OF: POST /api/v1/local/bench/runs/stop (M3 stop_route fixture).
    stopRun: () => Promise.resolve(),
    // FAKE-OF: GET /api/v1/local/bench/results (M3 results_route fixture).
    readResults: () => Promise.resolve(structuredClone(RESULT_ROWS)),
  };
}

function renderRealSettingsPage(client: LocalBenchClient): void {
  const route = SETTINGS_ROUTES.find((entry) => entry.path === 'localbench');
  if (route === undefined) {
    throw new Error('missing localbench settings route');
  }
  render(
    <SettingsLayout
      titleKey={route.titleKey}
      purposeKey={route.purposeKey}
      needItNowKey={route.needItNowKey}
    >
      <LocalBenchTab client={client} />
    </SettingsLayout>,
  );
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

describe('localbench settings route', () => {
  it('adds the localbench tab to the real route table with locale keys', () => {
    const route = SETTINGS_ROUTES.find((entry) => entry.path === 'localbench');
    expect(route?.titleKey).toBe('settings.localbench.title');
    expect(route?.purposeKey).toBe('settings.localbench.purpose');
    expect(route?.needItNowKey).toBe('settings.localbench.needItNow');
  });

  it('matches the frozen K05 M3 STEP1e route table', () => {
    expect(LOCALBENCH_ENDPOINTS.scan).toBe('/api/v1/local/bench/scan');
    expect(LOCALBENCH_ENDPOINTS.estimate).toBe('/api/v1/local/bench/estimate');
    expect(LOCALBENCH_ENDPOINTS.runs).toBe('/api/v1/local/bench/runs');
    expect(LOCALBENCH_ENDPOINTS.pause).toBe('/api/v1/local/bench/runs/pause');
    expect(LOCALBENCH_ENDPOINTS.resume).toBe(
      '/api/v1/local/bench/runs/resume',
    );
    expect(LOCALBENCH_ENDPOINTS.stop).toBe('/api/v1/local/bench/runs/stop');
    expect(LOCALBENCH_ENDPOINTS.results).toBe('/api/v1/local/bench/results');
    expect(expandBenchScan(LOCALBENCH_ENDPOINTS.scan, 'bench-cases')).toBe(
      '/api/v1/local/bench/scan?path=bench-cases',
    );
    expect(
      expandBenchEstimate(LOCALBENCH_ENDPOINTS.estimate, 'local-b', 'deep'),
    ).toBe('/api/v1/local/bench/estimate?model_id=local-b&level=Deep');
    expect(expandBenchEstimate(LOCALBENCH_ENDPOINTS.estimate, 'm', 'quick')).toBe(
      '/api/v1/local/bench/estimate?model_id=m&level=Quick',
    );
    expect(expandBenchResults(LOCALBENCH_ENDPOINTS.results, 'run-1')).toBe(
      '/api/v1/local/bench/results?run_id=run-1',
    );
    expect(toWireRunBody({ model_id: 'm', level: 'quick' })).toEqual({
      model_id: 'm',
      level: 'Quick',
    });
  });

  it('HttpLocalBenchClient scans through the M3 scan route', async () => {
    const seen: string[] = [];
    vi.stubGlobal('fetch', async (url: unknown) => {
      seen.push(String(url));
      return new Response(JSON.stringify(SCAN_IDS), { status: 200 });
    });
    const client = new HttpLocalBenchClient();
    const result = await client.scanModels('bench-cases');
    expect(seen).toEqual(['/api/v1/local/bench/scan?path=bench-cases']);
    expect(result.path).toBe('bench-cases');
    expect(result.models).toEqual([
      { model_id: 'local-a', display_name: 'local-a', evidence: 'UNKNOWN' },
      { model_id: 'local-b', display_name: 'local-b', evidence: 'UNKNOWN' },
    ]);
  });

  it('HttpLocalBenchClient reads the M3 estimate route', async () => {
    const seen: string[] = [];
    vi.stubGlobal('fetch', async (url: unknown) => {
      seen.push(String(url));
      return new Response(
        JSON.stringify({
          level: 'Deep',
          model_id: 'local-b',
          minutes_min: 10,
          minutes_max: 15,
        }),
        { status: 200 },
      );
    });
    const client = new HttpLocalBenchClient();
    const estimate = await client.readEstimate('local-b', 'deep');
    expect(seen).toEqual([
      '/api/v1/local/bench/estimate?model_id=local-b&level=Deep',
    ]);
    expect(estimate).toEqual({
      model_id: 'local-b',
      level: 'deep',
      minutes_min: 10,
      minutes_max: 15,
    });
  });

  it('HttpLocalBenchClient starts, pauses, resumes and stops runs', async () => {
    const seen: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal(
      'fetch',
      async (url: unknown, init?: { body?: string }) => {
        seen.push({
          url: String(url),
          body:
            init?.body === undefined ? undefined : JSON.parse(init.body),
        });
        const isRun = String(url) === LOCALBENCH_ENDPOINTS.runs;
        return new Response(isRun ? JSON.stringify(RUN_ID) : null, {
          status: 200,
        });
      },
    );
    const client = new HttpLocalBenchClient();
    await expect(
      client.startRun({ model_id: 'm', level: 'quick' }),
    ).resolves.toBe(RUN_ID);
    await client.pauseRun(RUN_ID);
    await client.resumeRun(RUN_ID);
    await client.stopRun(RUN_ID);
    expect(seen).toEqual([
      {
        url: '/api/v1/local/bench/runs',
        body: { model_id: 'm', level: 'Quick' },
      },
      { url: '/api/v1/local/bench/runs/pause', body: { run_id: RUN_ID } },
      { url: '/api/v1/local/bench/runs/resume', body: { run_id: RUN_ID } },
      { url: '/api/v1/local/bench/runs/stop', body: { run_id: RUN_ID } },
    ]);
  });

  it('HttpLocalBenchClient reads the M3 results rows', async () => {
    const seen: string[] = [];
    vi.stubGlobal('fetch', async (url: unknown) => {
      seen.push(String(url));
      return new Response(JSON.stringify(RESULT_ROWS), { status: 200 });
    });
    const client = new HttpLocalBenchClient();
    const rows = await client.readResults('run-1');
    expect(seen).toEqual(['/api/v1/local/bench/results?run_id=run-1']);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.case_id).toBe('q01');
    expect(rows[0]?.kind).toBe('MEASURED');
    expect(rows[0]?.hardware.cpu_only).toBe(true);
  });
});

describe('LocalBenchTab on the real settings page', () => {
  it('runs path -> scan -> level -> run with warnings, results and a decision record', async () => {
    renderRealSettingsPage(makeFakeClient());
    expect(screen.getByText(EN_LOCALBENCH.title)).toBeTruthy();

    fireEvent.change(screen.getByTestId('localbench-path'), {
      target: { value: 'bench-cases' },
    });
    fireEvent.click(screen.getByTestId('localbench-scan'));
    expect(await screen.findByText('local-a')).toBeTruthy();
    expect(screen.getByText('local-b')).toBeTruthy();

    fireEvent.click(screen.getByTestId('localbench-model-local-b'));
    fireEvent.click(screen.getByTestId('localbench-level-deep'));
    fireEvent.click(screen.getByTestId('localbench-run'));

    const outcome = await screen.findByTestId('localbench-outcome');
    expect(outcome.textContent).toContain(EN_LOCALBENCH.durationWarning);
    expect(outcome.textContent).toContain(EN_LOCALBENCH.loadWarning);
    expect(await screen.findByTestId('localbench-result-q02')).toBeTruthy();
    expect(screen.queryByTestId('localbench-result-q01')).toBeNull();

    const decisions = await screen.findByTestId('localbench-decisions');
    expect(decisions.textContent).toContain('local-b');
    expect(decisions.textContent).toContain('Deep');
    expect(decisions.textContent).toContain('Proxy');
  });

  it('shows the decision record title and models title from locale', async () => {
    renderRealSettingsPage(makeFakeClient());
    expect(screen.getByText(EN_LOCALBENCH.decisionTitle)).toBeTruthy();
    expect(screen.getByText(EN_LOCALBENCH.modelsTitle)).toBeTruthy();
    expect(screen.getByText(EN_LOCALBENCH.decisionEmpty)).toBeTruthy();
  });
});

describe('localbench locale parity', () => {
  it('adds the same real-text keys in en and uk', () => {
    expect(NEW_KEYS).toHaveLength(33);
    expect(Object.keys(UK_LOCALBENCH).sort()).toEqual(
      Object.keys(EN_LOCALBENCH).sort(),
    );
    for (const leaf of Object.keys(EN_LOCALBENCH)) {
      expect(t(`settings.localbench.${leaf}`)).toBe(EN_LOCALBENCH[leaf]);
    }
    setLocale('uk');
    for (const leaf of Object.keys(UK_LOCALBENCH)) {
      expect(t(`settings.localbench.${leaf}`)).toBe(UK_LOCALBENCH[leaf]);
    }
  });

  it('keeps en ASCII-only and uk values non-empty', () => {
    for (const value of Object.values(EN_LOCALBENCH)) {
      expect(value).not.toMatch(/[\u0400-\u04FF]/);
      expect(value.length).toBeGreaterThan(0);
      expect(value).not.toMatch(/TODO|FIXME|NotImplemented/);
    }
    for (const value of Object.values(UK_LOCALBENCH)) {
      expect(value.length).toBeGreaterThan(0);
    }
  });
});
