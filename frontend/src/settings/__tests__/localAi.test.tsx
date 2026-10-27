/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import { ENDPOINTS } from "../../api/endpoints";
import { App } from "../../app/App";
import { SettingsLayout } from "../../shell/SettingsLayout";
import { LocalBenchTab } from "../LocalBenchTab";
import type { LocalBenchClient } from "../../settings/LocalBenchClient";
import type {
  BenchmarkLevel,
  LocalBenchEstimate,
  LocalBenchResultRow,
} from "../../settings/LocalBenchTypes";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";

type LocaleTable = { settings: { localbench: Record<string, string> } };
const EN_LOCALBENCH: Record<string, string> = (en as unknown as LocaleTable)
  .settings.localbench;
const UK_LOCALBENCH: Record<string, string> = (uk as unknown as LocaleTable)
  .settings.localbench;

// FAKE-OF: GET /api/v1/local/bench/scan (M3 scan_route ids fixture).
const SCAN_IDS = ["local-a", "local-b"];

// FAKE-OF: GET /api/v1/local/bench/estimate (M3 BenchEstimate fixture).
function fakeEstimate(
  modelId: string,
  level: BenchmarkLevel,
): LocalBenchEstimate {
  switch (level) {
    case "quick":
      return { model_id: modelId, level, minutes_min: 1, minutes_max: 2 };
    case "standard":
      return { model_id: modelId, level, minutes_min: 30, minutes_max: 40 };
    case "deep":
      return { model_id: modelId, level, minutes_min: 10, minutes_max: 15 };
  }
}

// FAKE-OF: POST /api/v1/local/bench/runs (M3 runs_route fixture).
const RUN_ID = "run-1";

// FAKE-OF: GET /api/v1/local/bench/results (M3 BenchResultRow list).
const RESULT_ROWS: Array<LocalBenchResultRow> = [
  {
    case_id: "q01",
    kind: "MEASURED",
    model_id: "local-a",
    hardware: {
      gpu_vendor: "CPU-only",
      gpu_model: null,
      vram_mb: null,
      ram_mb: 16384,
      cpu_only: true,
    },
  },
  {
    case_id: "q02",
    kind: "PROXY",
    model_id: "local-b",
    hardware: {
      gpu_vendor: "CPU-only",
      gpu_model: null,
      vram_mb: null,
      ram_mb: 16384,
      cpu_only: true,
    },
  },
];

function makeFakeBenchClient(): LocalBenchClient {
  return {
    // FAKE-OF: GET /api/v1/local/bench/scan (M3 scan_route ids fixture).
    scanModels: (path: string) =>
      Promise.resolve({
        path,
        models: SCAN_IDS.map((model_id) => ({
          model_id,
          display_name: model_id,
          evidence: "UNKNOWN" as const,
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

function stubScheme(dark: boolean): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 375,
  });
  const matchMedia = (query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" && dark,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: matchMedia,
  });
}

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

async function driveBenchFlow(): Promise<void> {
  render(
    <SettingsLayout
      titleKey="settings.localbench.title"
      purposeKey="settings.localbench.purpose"
      needItNowKey="settings.localbench.needItNow"
    >
      <LocalBenchTab client={makeFakeBenchClient()} />
    </SettingsLayout>,
  );
  fireEvent.change(screen.getByTestId("localbench-path"), {
    target: { value: "bench-cases" },
  });
  fireEvent.click(screen.getByTestId("localbench-scan"));
  expect(await screen.findByText("local-a")).toBeTruthy();
  fireEvent.click(screen.getByTestId("localbench-model-local-b"));
  fireEvent.click(screen.getByTestId("localbench-level-deep"));
  fireEvent.click(screen.getByTestId("localbench-run"));
  expect(await screen.findByTestId("localbench-decisions")).toBeTruthy();
  cleanup();
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe.each([false, true])("localAi settings view (dark=%s)", (dark) => {
  it("renders stored config plus the registry endpoint plus the decision record", async () => {
    stubScheme(dark);
    await driveBenchFlow();
    renderAppAt("/settings/localAI");
    const stored = await screen.findByTestId("localai-stored");
    expect(stored.textContent).toContain("bench-cases");
    expect(stored.textContent).toContain("local-a");
    expect(stored.textContent).toContain(EN_LOCALBENCH.modelsTitle);
    expect(screen.getByTestId("localai-endpoint").textContent).toBe(
      ENDPOINTS.agentsLive,
    );
    const decisions = await screen.findByTestId("localbench-decisions");
    expect(decisions.textContent).toContain("local-b");
    expect(decisions.textContent).toContain(EN_LOCALBENCH.levelDeep);
    expect(decisions.textContent).toContain(EN_LOCALBENCH.evidenceProxy);
  });

  it("stays non-empty with honest empty states when nothing was stored", async () => {
    stubScheme(dark);
    renderAppAt("/settings/localAI");
    const stored = await screen.findByTestId("localai-stored");
    expect(stored.textContent).toContain(EN_LOCALBENCH.modelsEmpty);
    expect(stored.textContent).toContain(EN_LOCALBENCH.decisionEmpty);
    expect(screen.getByTestId("localai-endpoint").textContent).toBe(
      ENDPOINTS.agentsLive,
    );
  });

  it("shows stored config plus endpoint next to unchanged placement buckets", async () => {
    stubScheme(dark);
    await driveBenchFlow();
    renderAppAt("/projects/p-1/local-ai");
    expect(await screen.findByTestId("place-row-agent-1")).toBeTruthy();
    const stored = await screen.findByTestId("localai-stored");
    expect(stored.textContent).toContain("bench-cases");
    expect(screen.getByTestId("localai-endpoint").textContent).toBe(
      ENDPOINTS.agentsLive,
    );
    expect(await screen.findByTestId("localbench-decisions")).toBeTruthy();
  });

  it("keeps every other settings section body empty", async () => {
    stubScheme(dark);
    renderAppAt("/settings/models");
    expect(await screen.findByTestId("settings-section-body")).toBeTruthy();
    expect(screen.queryByTestId("localai-stored")).toBeNull();
  });

  it("renders the same stored strings through the uk locale", async () => {
    stubScheme(dark);
    setLocale("uk");
    await driveBenchFlow();
    cleanup();
    renderAppAt("/settings/localAI");
    const stored = await screen.findByTestId("localai-stored");
    expect(stored.textContent).toContain(UK_LOCALBENCH.modelsTitle);
    expect(stored.textContent).toContain(UK_LOCALBENCH.decisionTitle);
    expect(stored.textContent).not.toContain(UK_LOCALBENCH.decisionEmpty);
    expect(screen.getByTestId("localai-endpoint").textContent).toBe(
      ENDPOINTS.agentsLive,
    );
    expect(t("settings.localAi.title")).toBe(
      (uk as unknown as { settings: { localAi: { title: string } } }).settings
        .localAi.title,
    );
  });
});
