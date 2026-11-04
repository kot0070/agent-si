// FXROLEPICK R5: with a connected local runtime Scan and Run work
// with no folder (fake local server at the network only). Pick a path
// or a runtime, Scan, Run stays disabled until a scan with the reason
// shown; the run shows progress and its result rows or a plain
// failure.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import type {
  BenchmarkLevel,
  LocalBenchEstimate,
  LocalBenchModel,
} from "../LocalBenchTypes";
import type { LocalBenchClient } from "../LocalBenchClient";
import { LocalBenchTab } from "../LocalBenchTab";

const RUN_ID = "run-r5";

function fakeEstimate(modelId: string, level: BenchmarkLevel): LocalBenchEstimate {
  return { model_id: modelId, level, minutes_min: 1, minutes_max: 2 };
}

const RUNTIME_MODELS: LocalBenchModel[] = [
  { model_id: "ollama/llama3.2", display_name: "llama3.2", evidence: "UNKNOWN" },
  { model_id: "ollama/mistral-7b", display_name: "mistral-7b", evidence: "UNKNOWN" },
];

const RESULT_ROWS = [
  {
    case_id: "case-1",
    kind: "MEASURED" as const,
    model_id: "ollama/llama3.2",
    hardware: { gpu_vendor: "CPU-only", gpu_model: null, vram_mb: null, ram_mb: 8192, cpu_only: true },
  },
];

function stubNetwork(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/v1/providers") {
        return new Response(JSON.stringify({ providers: [] }), { status: 200 });
      }
      if (url === "/api/v1/local/models") {
        return new Response(
          JSON.stringify([
            { model: "http://localhost:11434", evidence_tier: "PROXY", status: "READY" },
          ]),
          { status: 200 },
        );
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

function makeFakeClient(): LocalBenchClient {
  return {
    scanModels: (path: string) =>
      Promise.resolve({ path, models: [] }),
    scanRuntimeModels: (presetId: string) =>
      Promise.resolve({ path: `runtime:${presetId}`, models: RUNTIME_MODELS }),
    readEstimate: (modelId: string, level: BenchmarkLevel) =>
      Promise.resolve(fakeEstimate(modelId, level)),
    startRun: () => Promise.resolve(RUN_ID),
    pauseRun: () => Promise.resolve(),
    resumeRun: () => Promise.resolve(),
    stopRun: () => Promise.resolve(),
    readResults: () => Promise.resolve(structuredClone(RESULT_ROWS)),
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  stubNetwork();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R5 bench with a connected local runtime", () => {
  it("scans the runtime with no folder and runs with progress to result rows", async () => {
    render(<LocalBenchTab client={makeFakeClient()} />);
    expect(await screen.findByTestId("localbench-source-ollama")).toBeTruthy();
    expect(screen.getByTestId("localbench-scan").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("localbench-run").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTestId("localbench-run-reason").textContent).toContain(
      "Run is disabled until a scan finishes.",
    );
    fireEvent.click(screen.getByTestId("localbench-source-ollama"));
    expect(screen.getByTestId("localbench-scan").hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByTestId("localbench-scan"));
    expect(await screen.findByTestId("localbench-model-ollama/llama3.2")).toBeTruthy();
    expect(screen.queryByTestId("localbench-run-reason")).toBeNull();
    fireEvent.click(screen.getByTestId("localbench-run"));
    expect(await screen.findByTestId("localbench-outcome")).toBeTruthy();
    expect(await screen.findByTestId("localbench-result-case-1")).toBeTruthy();
  });

  it("a failing run reads a plain failure", async () => {
    const client = makeFakeClient();
    client.readResults = () => Promise.reject(new Error("boom"));
    render(<LocalBenchTab client={client} />);
    fireEvent.click(await screen.findByTestId("localbench-source-ollama"));
    fireEvent.click(screen.getByTestId("localbench-scan"));
    await screen.findByTestId("localbench-model-ollama/llama3.2");
    fireEvent.click(screen.getByTestId("localbench-run"));
    await screen.findByText("Something went wrong. Try again.");
  });
});
