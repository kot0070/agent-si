/** @vitest-environment jsdom */
// FXDESIGN8 behaviour proofs (RED first, row testids kept):
// 1. team one-liner (role, short model, status chip, step) with the rest
//    under a disclosure; finished rows stay with real state, never Unknown.
// 2. results Open is a quiet text link on the name line, never a box.
// 3. results/tokens/team read the runs key: verdict + files, per-kind
//    tokens, last run team; unknown renders one quiet line, never 0/Unknown.
// 4. one shared agents-live store: a single interval for every subscriber.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { ReactElement } from "react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { Inspector } from "../Inspector";
import { TopBar } from "../TopBar";
import { AgentsLive } from "../../agents/AgentsLive";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const PROJECT = {
  project_id: "p-1",
  name: "P1",
  created_at: "2026-02-11T06:42:44Z",
};

const LIVE_MIXED = {
  agents: [
    {
      agent: "agent-1",
      scope: "scope-1",
      deliverable: "part-1",
      status: "RUNNING",
      role: "manager",
      provider: "meta",
      model: "meta-llama/long-model-name-70b",
      step: 2,
      file: "f-1.ts",
      last_action: "edited hello",
      tokens: { input: 4000, output: 912 },
      context: 4912,
      window: 1000000,
      errors: [],
      waits: [],
    },
    {
      agent: "agent-2",
      scope: "scope-2",
      deliverable: "part-2",
      status: "RETURNED",
      role: "worker",
      provider: "meta",
      model: "m-2",
      step: 4,
      file: "hello.txt",
      last_action: "wrote hello",
      tokens: { input: 100, output: 50 },
      context: 150,
      window: 1000000,
      errors: [],
      waits: [],
    },
    {
      agent: "agent-3",
      scope: "scope-3",
      deliverable: "part-3",
      status: "QUEUED",
    },
  ],
};

const LIVE_IDLE = {
  agents: [
    {
      agent: "agent-1",
      scope: "scope-1",
      deliverable: "part-1",
      status: "RETURNED",
      role: "manager",
      provider: "meta",
      model: "meta-llama/long-model-name-70b",
      step: 4,
      file: "hello.txt",
      last_action: "wrote hello",
      tokens: { input: 4000, output: 912 },
      context: 4912,
      window: 1000000,
      errors: [],
      waits: [],
    },
    {
      agent: "agent-2",
      scope: "scope-2",
      deliverable: "part-2",
      status: "QUEUED",
    },
  ],
};

const RUNS_LEDGER = {
  rows: [
    { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
  ],
  runs: [
    {
      run_id: "run-7",
      project: "p-1",
      task: "say hi",
      title: "Say hi to the owner",
      start: "2026-02-11T06:40:00Z",
      end: "2026-02-11T06:42:44Z",
      success: true,
      stopped: false,
      summary: "greeted the owner",
      parts: [],
      verdicts: {},
      tokens: 4912,
      cost: "UNKNOWN",
      files: ["hello.txt"],
    },
  ],
};

const TELEMETRY = {
  metric_records: 3,
  telemetry_events: 9,
  totals: { tokens_total: 4912, cloud_calls: 9 },
  tasks: ["say hi"],
  models: [{ model: "m-8", calls: 2, tokens: 4912, cost: "UNAVAILABLE" }],
  providers: [{ provider: "meta", calls: 2, tokens: 4912, cost: "UNAVAILABLE" }],
};

function stubFx8(options?: {
  telemetry?: boolean;
  live?: typeof LIVE_MIXED;
}): void {
  const withTelemetry = options?.telemetry ?? true;
  const live = options?.live ?? LIVE_MIXED;
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p-1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody(live);
      }
      if (method === "GET" && url.startsWith("/api/v1/runs/ledger")) {
        return jsonBody(RUNS_LEDGER);
      }
      if (method === "GET" && url.startsWith("/api/v1/tasks")) {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/budget")) {
        return jsonBody({ project_id: "p-1", budget: null });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/status")) {
        return jsonBody({
          project_id: "p-1",
          integrity_ok: true,
          journal_head: "evt-0042",
          generated_at: "2026-02-11T06:42:44Z",
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/journal")) {
        return jsonBody([
          {
            entry_id: "evt-0042",
            timestamp: "2026-02-11T06:42:44Z",
            hash: "h-42",
          },
        ]);
      }
      if (method === "GET" && url.startsWith("/api/v1/apps/card")) {
        return jsonBody({
          project_id: "p-1",
          service_ids: [],
          paused: false,
          generated_at: "t-0",
        });
      }
      if (
        withTelemetry &&
        method === "GET" &&
        url.startsWith("/api/v1/analytics/telemetry")
      ) {
        return jsonBody(TELEMETRY);
      }
      return jsonBody({ code: "FXDESIGN8_UNEXPECTED_API" }, 404);
    },
  );
}

function renderInspector(): void {
  const router = createMemoryRouter([{ path: "*", element: <InspectorShell /> }], {
    initialEntries: ["/"],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function InspectorShell(): ReactElement {
  return <Inspector projectId="p-1" live={<span>live</span>} />;
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.locale", "en");
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxdesign8 team one-liner", () => {
  it("shows role, short model and status on one line; step in details; full model in the tooltip", async () => {
    stubFx8();
    renderInspector();
    const row = await screen.findByTestId("team-row-agent-1");
    const line = await screen.findByTestId("team-line-agent-1");
    // FXLOOK D5: human summary (role, status), never the raw agent id
    // or the full model id in the line text.
    expect(line.textContent).toContain(t("providers.role.manager"));
    expect(line.textContent).toContain(t("tasks.status.running"));
    // FXFACTS F14: the one-line row is role, short model, status; the
    // step, attempts and placement moved into the details.
    expect(line.textContent).not.toContain("agent-1");
    expect(line.textContent).not.toContain("meta-llama/long-model-name-70b");
    expect(line.getAttribute("title")).toBe("meta-llama/long-model-name-70b");
    expect(line.textContent).not.toContain("2");
    // The raw id and the full model live under the row disclosure.
    const detail = await screen.findByTestId("team-detail-agent-1");
    expect(detail.textContent).toContain("agent-1");
    expect(detail.textContent).toContain("meta-llama/long-model-name-70b");
    expect(detail.textContent).toContain("scope-1");
    expect(detail.textContent).toContain("edited hello");
    expect(detail.textContent).toContain("2");
  });

  it("keeps finished rows with real state and no Unknown chip", async () => {
    stubFx8();
    renderInspector();
    const row = await screen.findByTestId("team-row-agent-2");
    expect(row.textContent).toContain(t("tasks.status.returned"));
    expect(row.textContent).not.toContain(t("shell.common.unknown"));
    expect(screen.queryByTestId("team-place-agent-2")).toBeNull();
  });

  it("renders no Unknown chip for a bare row while a run is live", async () => {
    stubFx8();
    renderInspector();
    const row = await screen.findByTestId("team-row-agent-3");
    expect(row.textContent).not.toContain(t("shell.common.unknown"));
    expect(screen.queryByTestId("team-place-agent-3")).toBeNull();
  });
});

describe("fxdesign8 results from the runs key", () => {
  it("shows the last run verdict plus files with a quiet open link", async () => {
    stubFx8();
    renderInspector();
    // FXFACTS F10: Results renders closed; the card under test is opened.
    fireEvent.click(await screen.findByTestId("rail-toggle-results"));
    const verdict = await screen.findByTestId("result-last-verdict");
    // FXZERO R2: the task title (or a short human name) is primary;
    // the raw run id rides the details only (tooltip), never the text.
    expect(verdict.textContent).toContain("Say hi to the owner");
    expect(verdict.textContent).toContain("greeted the owner");
    expect(verdict.textContent).not.toContain("run-7");
    expect(verdict.getAttribute("title")).toContain("run-7");
    const files = await screen.findByTestId("result-last-files");
    expect(files.textContent).toContain("hello.txt");
    const open = await screen.findByTestId("result-open-run-7");
    expect(open.getAttribute("href")).toBe("/projects/p-1/reports");
    // Quiet text link on the name line: never the tall boxed button.
    expect(open.className).not.toContain("fx-btn-quiet");
    expect(open.className).toContain("fx-why-quiet");
  });
});

describe("fxdesign8 tokens from served totals", () => {
  it("idle shows the last run total, matching the chat Total line", async () => {
    stubFx8({ telemetry: true, live: LIVE_IDLE });
    renderInspector();
    // FXFACTS F10: metric cards live in More and Context renders closed.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    fireEvent.click(await screen.findByTestId("rail-toggle-context"));
    // No run live: the rail reads the runs key, not the ended live rows
    // (which would sum a different number) and never an invented zero.
    const card = await screen.findByTestId("kit-metric-fx-tokens");
    expect(card.textContent).toContain("4,912");
    expect(card.textContent).not.toContain("5,062");
    // Per-model legend from the telemetry doc, raw model names.
    const legend = await screen.findByTestId("ctx-legend");
    expect(legend.textContent).toContain("m-8");
    expect(legend.textContent).toContain("4,912");
    expect(await screen.findByTestId("ctx-used")).toBeTruthy();
  });

  it("live shows live-row sums with the per-role legend", async () => {
    stubFx8({ telemetry: true, live: LIVE_MIXED });
    renderInspector();
    // FXFACTS F10: metric cards live in More and Context renders closed.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    fireEvent.click(await screen.findByTestId("rail-toggle-context"));
    const card = await screen.findByTestId("kit-metric-fx-tokens");
    expect(card.textContent).toContain("5,062");
    const legend = await screen.findByTestId("ctx-legend");
    expect(legend.textContent).toContain("4,912");
  });

  it("renders one quiet line when no token source is served", async () => {
    stubFx8({ telemetry: false });
    vi.stubGlobal(
      "fetch",
      async (input: unknown, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        if ((init?.method ?? "GET").toUpperCase() === "GET") {
          if (url === "/api/v1/projects") {
            return jsonBody({ projects: [PROJECT] });
          }
          if (url === "/api/v1/agents/live") {
            return jsonBody({ agents: [] });
          }
          if (url.startsWith("/api/v1/runs/ledger")) {
            return jsonBody({ rows: [] });
          }
        }
        return jsonBody({ code: "FXDESIGN8_UNEXPECTED_API" }, 404);
      },
    );
    renderInspector();
    // FXFACTS F10: the tokens card lives in More; with no token source
    // it stays closed on its quiet dash with no toggle.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    const quiet = await screen.findByTestId("tokens-unknown");
    expect(quiet.textContent).toBe(t("shell.cards.context.noUsage"));
    // The card shell stays on its one-line dash; its total is Unknown,
    // never an invented zero.
    const card = await screen.findByTestId("kit-metric-fx-tokens");
    expect(card.textContent).toContain("—");
    expect(screen.queryByTestId("kit-toggle-fx-tokens")).toBeNull();
  });
});

describe("fxdesign8 shared agents-live store", () => {
  it("polls once for top bar, inspector and the live page together", async () => {
    vi.useFakeTimers();
    try {
      const seen: string[] = [];
      vi.stubGlobal(
        "fetch",
        async (input: unknown, init?: RequestInit): Promise<Response> => {
          const url = String(input);
          const method = (init?.method ?? "GET").toUpperCase();
          if (url === "/api/v1/agents/live" && method === "GET") {
            seen.push(url);
            return jsonBody({ agents: [] });
          }
          if (url === "/api/v1/projects" && method === "GET") {
            return jsonBody({ projects: [PROJECT] });
          }
          if (url === "/api/v1/projects/p-1" && method === "GET") {
            return jsonBody({ project: PROJECT });
          }
          return jsonBody({ code: "FXDESIGN8_UNEXPECTED_API" }, 404);
        },
      );
      const router = createMemoryRouter(
        [
          {
            path: "/",
            element: (
              <>
                <TopBar projectId="p-1" />
                <Inspector projectId="p-1" live={<span>live</span>} />
                <AgentsLive projectId="p-1" />
              </>
            ),
          },
        ],
        { initialEntries: ["/"] },
      );
      render(
        <ApiClientProvider client={new HttpApiClient()}>
          <RouterProvider router={router} />
        </ApiClientProvider>,
      );
      await vi.advanceTimersByTimeAsync(7000);
      const liveCalls = seen.filter(
        (url) => url === "/api/v1/agents/live",
      ).length;
      // One shared poller: initial load plus one 3 s tick each 3 s.
      expect(liveCalls).toBeLessThanOrEqual(4);
    } finally {
      vi.useRealTimers();
    }
  });
});
