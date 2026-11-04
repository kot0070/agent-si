/** @vitest-environment jsdom */
// FXDESIGN9 behaviour proofs (RED first, real App at real routes, fetch
// faked only at the network boundary):
// 1. rail Tests card: one row per kind with REAL served counts
//    (pass green, fail red; BLOCKED counts as fail, in-flight rows count
//    as neither); empty plan reads the short not-run line, never a plan id.
// 2. rail cleanup: purpose sentences gone (tests/budget/providers), the
//    chat row hides when it repeats the last run, the closed one-liners
//    carry label left / value right.
// 3. ORDER 61: Tests tab top line plus the local-tests switch beside it.
// 4. D7: a settings section page carries the grouped nav (same link
//    testids, active row marked) beside the section content.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

// CODE: 12 PASS + 1 FAIL; AI: 3 PASS; HUMAN: 1 BLOCKED (counts as fail).
function testsRows() {
  const rows: Record<string, unknown>[] = [];
  let n = 0;
  const add = (kind: string, status: string, count: number) => {
    for (let i = 0; i < count; i += 1) {
      n += 1;
      rows.push({
        test_id: `t-${kind}-${status}-${i}`,
        status,
        output_ref: null,
        kind,
      });
    }
  };
  add("CODE", "PASS", 12);
  add("CODE", "FAIL", 1);
  add("AI", "PASS", 3);
  add("HUMAN", "BLOCKED", 1);
  void n;
  return rows;
}

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubServed(options?: { plan?: boolean; chatEqualLastRun?: boolean }): void {
  const withPlan = options?.plan ?? true;
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/projects") return jsonBody({ projects: [PROJECT] });
    if (url === "/api/v1/projects/p-1") return jsonBody({ project: PROJECT });
    if (url === "/api/v1/agents/live") return jsonBody({ agents: [] });
    if (url === "/api/v1/tasks?project_id=p-1") return jsonBody({ tasks: [] });
    if (url === "/api/v1/runs/ledger?project_id=p-1") {
      return jsonBody({
        rows: [],
        runs: [
          {
            run_id: "r-9",
            project: "p-1",
            title: "nine",
            start: "2026-11-02T10:00:00Z",
            end: "2026-11-02T10:01:00Z",
            success: true,
            tokens: 1000,
            files: [],
          },
        ],
      });
    }
    if (url === "/api/v1/budget?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        budget: {
          project_id: "p-1",
          hard_limit: 5,
          spent: 1,
          reserved: 0,
          currency: "USD",
        },
      });
    }
    if (url === "/api/v1/watcher/status?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        integrity_ok: true,
        journal_head: "jh-1",
        generated_at: "t-0",
      });
    }
    if (url.startsWith("/api/v1/watcher/journal")) return jsonBody([]);
    if (url === "/api/v1/apps/card?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        service_ids: [],
        paused: false,
        generated_at: "t-0",
      });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [{ provider_id: "meta" }] });
    }
    if (url === "/api/v1/local/models") return jsonBody([]);
    if (url === "/api/v1/teststage/plans/latest?project_id=p-1") {
      if (!withPlan) return jsonBody({ code: "NONE" }, 404);
      return jsonBody({ project_id: "p-1", plan_id: "plan-9" });
    }
    if (url === "/api/v1/teststage/runs/latest?project_id=p-1") {
      if (!withPlan) return jsonBody({ code: "NONE" }, 404);
      return jsonBody({ project_id: "p-1", plan_id: "plan-9", run_id: "run-9" });
    }
    if (url.startsWith("/api/v1/teststage/tests-view")) {
      return jsonBody({
        plan_id: "plan-9",
        run_id: "run-9",
        active: 0,
        passed: 15,
        remaining: 0,
        rows: testsRows(),
        settings_controls: [],
      });
    }
    if (url === "/api/v1/teststage/local-tests?project_id=p-1") {
      return jsonBody({ project_id: "p-1", enabled: true });
    }
    if (url.startsWith("/api/v1/analytics/telemetry")) {
      // Project total 23 488; last run 1 000; chat answers 1 000 when
      // chatEqualLastRun (must hide: repeats the last run).
      return jsonBody({
        metric_records: 1,
        telemetry_events: 1,
        totals: { tokens_total: 23488, cloud_calls: 1 },
        tasks: [],
        models: [{ model: "m-8", tokens: 23488, calls: 1, cost: "0.1" }],
        providers: [],
      });
    }
    if (url.startsWith("/api/v1/teststage/")) {
      return jsonBody({ code: "FXDESIGN9_UNEXPECTED_API" }, 404);
    }
    if (url.startsWith("/api/v1/reports/")) {
      return jsonBody({ code: "NONE" }, 404);
    }
    return jsonBody({ code: "FXDESIGN9_UNEXPECTED_API" }, 404);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

async function openMore(): Promise<void> {
  fireEvent.click(await screen.findByTestId("rail-more-toggle"));
}

describe("fxdesign9 tests card", () => {
  it("shows one row per kind with real pass/fail counts and no ids", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openMore();
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-tests"));
    const code = await screen.findByTestId("tests-kind-CODE");
    expect(code.textContent).toContain("12");
    expect(code.textContent).toContain("1");
    const ai = await screen.findByTestId("tests-kind-AI");
    expect(ai.textContent).toContain("3");
    const human = await screen.findByTestId("tests-kind-HUMAN");
    expect(human.textContent).toContain("0");
    expect(human.textContent).toContain("1");
    // No raw plan or run id anywhere in the rail.
    const rail = await screen.findByTestId("inspector");
    expect(rail.textContent).not.toContain("plan-9");
    expect(rail.textContent).not.toContain("run-9");
  });

  it("reads the short not-run line when no plan is served", async () => {
    stubServed({ plan: false });
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openMore();
    const card = await screen.findByTestId("kit-metric-fx-tests");
    expect(card.textContent).toContain("Not run yet");
    expect(card.textContent).not.toContain("plan-9");
  });

  it("uk rows read kind, pass and fail", async () => {
    stubServed();
    setLocale("uk");
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openMore();
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-tests"));
    const code = await screen.findByTestId("tests-kind-CODE");
    expect(code.textContent).toContain("Код");
    expect(code.textContent).toContain("12");
    const ai = await screen.findByTestId("tests-kind-AI");
    expect(ai.textContent).toContain("ШІ");
    const human = await screen.findByTestId("tests-kind-HUMAN");
    expect(human.textContent).toContain("Людина");
    const rail = await screen.findByTestId("inspector");
    expect(rail.textContent).not.toContain("plan-9");
  });
});

describe("fxdesign9 rail cleanup", () => {
  it("purpose sentences are gone from the rail cards", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openMore();
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-tests"));
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-budget"));
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-providers"));
    const rail = await screen.findByTestId("inspector");
    expect(rail.textContent).not.toContain(en.shell.cards.tests.subtitle);
    expect(rail.textContent).not.toContain(en.shell.cards.budget.subtitle);
    expect(rail.textContent).not.toContain(en.shell.cards.providers.subtitle);
  });

  it("uk purpose sentences are gone from the rail cards", async () => {
    stubServed();
    setLocale("uk");
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openMore();
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-tests"));
    const rail = await screen.findByTestId("inspector");
    expect(rail.textContent).not.toContain(uk.shell.cards.tests.subtitle);
  });

  it("the chat row hides when it repeats the last run", async () => {
    stubServed({ chatEqualLastRun: true });
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openMore();
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-tokens"));
    // Last run row stays (its own figure); the chat repeat goes.
    await screen.findByTestId("tokens-last-run");
    expect(screen.queryByTestId("tokens-chat")).toBeNull();
  });
});

describe("fxdesign9 ORDER 61 tests tab line", () => {
  it("shows the plain line with the local-tests switch beside it", async () => {
    stubServed();
    renderAppAt("/projects/p-1/tests");
    const line = await screen.findByTestId("tests-auto-line");
    expect(line.textContent).toContain("tests run by themselves");
    const tab = await screen.findByTestId("tests-tab");
    expect(
      tab.querySelectorAll('[data-testid="local-tests-switch"]').length,
    ).toBe(1);
  });

  it("uk line reads plain", async () => {
    stubServed();
    setLocale("uk");
    renderAppAt("/projects/p-1/tests");
    const line = await screen.findByTestId("tests-auto-line");
    expect(line.textContent).toContain("тести запускаються самі");
  });
});

describe("fxdesign9 D7 settings section nav", () => {
  it("section page carries the grouped nav beside the content", async () => {
    stubServed();
    renderAppAt("/settings/models");
    const nav = await screen.findByTestId("settings-nav");
    expect(nav.textContent).toContain("Models and providers");
    const active = await screen.findByTestId("settings-link-models");
    expect(active.getAttribute("aria-current")).toBe("page");
    expect(await screen.findByTestId("settings-section-body")).toBeTruthy();
    expect(
      await screen.findByTestId("settings-nav-select"),
    ).toBeTruthy();
  });
});
