/** @vitest-environment jsdom */
// FXDESIGN4: placement badges read row.placement (never a status guess);
// provider/step/tokens render from the run; the TopBar badge follows the
// live rows, the default route, or hides; stop-all carries actor "user"
// with a human result; bench estimate follows the selected model/level;
// the tests view board reads the latest plan/run per project.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import type { PartRow } from "../../api/iface";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import en from "../../locale/en.json";
import { AgentsLive } from "../../agents/AgentsLive";
import { TopBar } from "../../shell/TopBar";
import { BenchEstimateCard } from "../../k07next3/BenchEstimateCard";
import { TestsViewBoard } from "../../k07next3/TestsViewBoard";

function asRow(extra: Record<string, unknown>): PartRow {
  return extra as unknown as PartRow;
}

const MUSE_ROW = asRow({
  agent: "muse-1",
  scope: "fxdevrun:p/p1/director",
  deliverable: "artifact://run/r1/p1",
  status: "RUNNING",
  placement: "CLOUD",
  provider: "anthropic",
  model: "claude-x",
  step: 2,
  tokens: { input: 12, output: 34 },
});

const LOCAL_ROW = asRow({
  agent: "local-1",
  scope: "fxdevrun:p/p2/worker",
  deliverable: "artifact://run/r2/p2",
  status: "RUNNING",
  placement: "LOCAL",
  provider: "ollama",
  model: "llama-x",
  step: 1,
  tokens: { input: 3, output: 5 },
});

const BARE_ROW = asRow({
  agent: "bare-1",
  scope: "s-bare",
  deliverable: "d-bare",
  status: "QUEUED",
});

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const seen: string[] = [];
let stopPosts: string[] = [];

function stubFetch(stopReceipt: unknown): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: unknown }) => {
      const url = String(input);
      seen.push(url);
      if (url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (url === "/api/v1/stop-all" && (init?.method ?? "GET") === "POST") {
        stopPosts.push(typeof init?.body === "string" ? init.body : "");
        return jsonBody(stopReceipt);
      }
      throw new Error(`unexpected fetch ${url}`);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  stopPosts = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

function renderTopBar(client: FakeApiClient): void {
  render(
    <ApiClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <TopBar projectId="p-1" />
      </MemoryRouter>
    </ApiClientProvider>,
  );
}

describe("fxdesign4 placement truth badges", () => {
  it("renders CLOUD plus provider meta for a Muse run", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient({ liveRows: [MUSE_ROW] })}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-badge-CLOUD")).toBeTruthy();
    expect(
      (await screen.findByTestId("agent-badge-CLOUD")).textContent,
    ).toContain("1");
    expect(
      (await screen.findByTestId("agent-row-place-muse-1")).textContent,
    ).toBe(en.agents.badge.cloud);
    const row = await screen.findByTestId("agent-row-muse-1");
    expect(row.textContent).toContain("anthropic");
    expect(row.textContent).toContain("12/34");
    const scope = row.querySelector('[title="fxdevrun:p/p1/director"]');
    expect(scope?.textContent).toBe("director");
  });

  it("renders LOCAL for a fake local provider", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient({ liveRows: [LOCAL_ROW] })}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(
      (await screen.findByTestId("agent-row-place-local-1")).textContent,
    ).toBe(en.agents.badge.local);
    expect(
      (await screen.findByTestId("agent-badge-LOCAL")).textContent,
    ).toContain("1");
  });

  it("shows UNKNOWN text for a row without placement", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient({ liveRows: [BARE_ROW] })}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(
      (await screen.findByTestId("agent-row-place-bare-1")).textContent,
    ).toBe(en.shell.common.unknown);
  });
});

describe("fxdesign4 top badge truth", () => {
  it("shows the placement of the current live rows", async () => {
    stubFetch({ accepted: true, stopped_count: 0, reason: "" });
    renderTopBar(new FakeApiClient({ liveRows: [MUSE_ROW] }));
    expect((await screen.findByTestId("pairing-badge")).textContent).toBe(
      en.agents.badge.cloud,
    );
  });

  it("falls back to the default route with no running rows", async () => {
    vi.stubGlobal(
      "fetch",
      async (input: unknown) => {
        if (String(input) === "/api/v1/providers") {
          return jsonBody({ providers: [{ provider_id: "openai" }] });
        }
        throw new Error(`unexpected fetch ${String(input)}`);
      },
    );
    renderTopBar(new FakeApiClient({ liveRows: [] }));
    expect((await screen.findByTestId("pairing-badge")).textContent).toBe(
      en.agents.badge.cloud,
    );
  });

  it("hides the badge when neither live rows nor a route is sourced", async () => {
    stubFetch({ accepted: true, stopped_count: 0, reason: "" });
    renderTopBar(new FakeApiClient({ liveRows: [] }));
    const badge = await screen.findByTestId("pairing-badge");
    expect(badge.hasAttribute("hidden")).toBe(true);
  });
});

describe("fxdesign4 stop-all carries actor user with a human result", () => {
  it("posts actor user and shows the stopped count", async () => {
    // FXFACTS F12: one click stops at once, no confirmation dialog.
    stubFetch({
      accepted: true,
      stopped_count: 2,
      reason: "stop supervised by user",
    });
    renderTopBar(new FakeApiClient({}));
    fireEvent.click(await screen.findByTestId("topbar-stop-all"));
    const result = await screen.findByTestId("stop-all-result");
    expect(result.textContent).toContain("Stopped 2");
    expect(result.textContent).not.toContain("200");
    expect(stopPosts).toHaveLength(1);
    expect(JSON.parse(stopPosts[0] ?? "{}").actor).toBe("user");
  });

  it("shows refused plus the reason and never a bare code", async () => {
    stubFetch({ accepted: false, stopped_count: 0, reason: "actor refused" });
    renderTopBar(new FakeApiClient({}));
    fireEvent.click(await screen.findByTestId("topbar-stop-all"));
    const result = await screen.findByTestId("stop-all-result");
    expect(result.textContent).toContain("Refused");
    expect(result.textContent).toContain("actor refused");
  });
});

describe("fxdesign4 bench estimate follows the selection", () => {
  it("estimates the selected model plus the chosen level", async () => {
    vi.stubGlobal(
      "fetch",
      async (input: unknown) => {
        seen.push(String(input));
        if (
          String(input) ===
          "/api/v1/local/bench/estimate?model_id=m-bench&level=Deep"
        ) {
          return jsonBody({ level: "Deep", model_id: "m-bench", minutes_min: 1, minutes_max: 2 });
        }
        throw new Error(`unexpected fetch ${String(input)}`);
      },
    );
    render(<BenchEstimateCard modelId="m-bench" level="Deep" />);
    await screen.findByTestId("k07next3-bench-estimate");
    expect(seen).toContain(
      "/api/v1/local/bench/estimate?model_id=m-bench&level=Deep",
    );
    expect(
      screen.getByTestId("k07next3-bench-estimate-value").textContent,
    ).toBe("m-bench");
  });

  it("shows no estimate line when none is selected", async () => {
    vi.stubGlobal("fetch", async (input: unknown) => {
      seen.push(String(input));
      throw new Error(`unexpected fetch ${String(input)}`);
    });
    render(<BenchEstimateCard modelId={null} />);
    await screen.findByTestId("k07next3-bench-estimate");
    expect(screen.queryByTestId("k07next3-bench-estimate-value")).toBeNull();
    expect(seen.filter((url) => url.includes("/bench/estimate"))).toEqual([]);
  });
});

describe("fxdesign4 tests view reads the latest plan and run", () => {
  function stubView(planOk: boolean): void {
    vi.stubGlobal("fetch", async (input: unknown) => {
      const url = String(input);
      seen.push(url);
      if (url.startsWith("/api/v1/teststage/plans/latest")) {
        return planOk
          ? jsonBody({ project_id: "p-tvb", plan_id: "plan-9" })
          : new Response("no plan", { status: 404 });
      }
      if (url.startsWith("/api/v1/teststage/runs/latest")) {
        return jsonBody({ project_id: "p-tvb", plan_id: "plan-9", run_id: "run-9" });
      }
      if (url.startsWith("/api/v1/teststage/tests-view")) {
        return jsonBody({
          plan_id: "plan-9",
          run_id: "run-9",
          active: 0,
          passed: 0,
          remaining: 0,
          rows: [],
          settings_controls: [],
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
  }

  it("renders the served plan and run ids per project", async () => {
    stubView(true);
    render(<TestsViewBoard projectId="p-tvb" />);
    await screen.findByTestId("k07next3-tests-view");
    expect(screen.getByText("plan-9")).toBeTruthy();
    expect(screen.getByText("run-9")).toBeTruthy();
  });

  it("shows its empty text when no plan is stored", async () => {
    stubView(false);
    render(<TestsViewBoard projectId="p-tvb" />);
    const empty = await screen.findByTestId("k07next3-tests-view-empty");
    expect(empty.textContent).toContain(t("empty.generic"));
  });
});
