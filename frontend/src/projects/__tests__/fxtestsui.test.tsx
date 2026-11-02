/** @vitest-environment jsdom */
// FXTESTSUI lane test (RED->GREEN): Tests tab + ONE local-tests switch
// wired to the merged teststage read routes. Only global fetch is faked;
// the real components under test are TestsTab (tab) and ProjectView with
// the LocalTestsSwitch (settings area). Route path comes from the real
// App export so the tab mounts at the shipped path.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { TESTS_ROUTE_PATH } from "../../app/App";
import { HttpApiClient } from "../../api/client";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import { TestsTab } from "../TestsTab";
import {
  PROJECT_VIEWS,
  projectMenuTestId,
} from "../projectsApi";

const TOKEN = "tok-fxtestsui-01";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | null;
}

const seen: SeenRequest[] = [];
let testsViewCalls = 0;
let localTestsEnabled = true;

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubBoundary(): void {
  seen.length = 0;
  testsViewCalls = 0;
  localTestsEnabled = true;
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const headers = { ...((init?.headers ?? {}) as Record<string, string>) };
      const body =
        typeof init?.body === "string" ? (init.body as string) : null;
      seen.push({ url, method, headers, body });
      if (url === "/api/v1/projects/p-9" && method === "GET") {
        return jsonBody({
          project: { project_id: "p-9", name: "Nine", created_at: CREATED_AT },
        });
      }
      if (url === "/api/v1/tasks?project_id=p-9" && method === "GET") {
        return jsonBody({ tasks: [] });
      }
      if (url === "/api/v1/runs/ledger?project_id=p-9" && method === "GET") {
        return jsonBody({ rows: [] });
      }
      if (url === "/api/v1/budget?project_id=p-9" && method === "GET") {
        return jsonBody({
          project_id: "p-9",
          budget: {
            project_id: "p-9",
            hard_limit: 100,
            spent: 10,
            reserved: 5,
            currency: "u-9",
          },
        });
      }
      if (url === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      if (
        url === "/api/v1/teststage/local-tests?project_id=p-9" &&
        method === "GET"
      ) {
        return jsonBody({ project_id: "p-9", enabled: localTestsEnabled });
      }
      if (url === "/api/v1/teststage/local-tests" && method === "POST") {
        const parsed = body === null ? {} : (JSON.parse(body) as Record<string, unknown>);
        localTestsEnabled = parsed["enabled"] === true;
        return jsonBody({
          project_id: "p-9",
          enabled: localTestsEnabled,
          updated_at: "",
        });
      }
      if (
        url === "/api/v1/teststage/plans/latest?project_id=p-7" &&
        method === "GET"
      ) {
        return jsonBody({ project_id: "p-7", plan_id: "plan-7" });
      }
      if (
        url === "/api/v1/teststage/runs/latest?project_id=p-7" &&
        method === "GET"
      ) {
        return jsonBody({
          project_id: "p-7",
          plan_id: "plan-7",
          run_id: "run-7",
        });
      }
      if (
        url === "/api/v1/teststage/tests-view?plan_id=plan-7&run_id=run-7" &&
        method === "GET"
      ) {
        testsViewCalls += 1;
        const finished = testsViewCalls >= 3;
        return jsonBody({
          plan_id: "plan-7",
          run_id: "run-7",
          active: 2,
          passed: finished ? 2 : 1,
          remaining: finished ? 0 : 1,
          rows: [
            {
              test_id: "t-boot",
              status: "PASS",
              output_ref: "evidence://p-7/out-1",
              kind: "CODE",
            },
            {
              test_id: "t-chat",
              status: finished ? "PASS" : "BLOCKED",
              output_ref: null,
              kind: "AI",
              reason: finished ? null : "needs chat provider",
            },
          ],
          settings_controls: [],
        });
      }
      if (
        url ===
          "/api/v1/teststage/result-output?ref=" +
            encodeURIComponent("evidence://p-7/out-1") &&
        method === "GET"
      ) {
        return jsonBody({
          ref: "evidence://p-7/out-1",
          project_id: "p-7",
          output: "boot ok\nline two",
          size: 18,
        });
      }
      if (
        url === "/api/v1/teststage/plans/latest?project_id=p-empty" &&
        method === "GET"
      ) {
        return jsonBody({ code: "CONTEXT_MISSING" }, 404);
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  clearUiToken();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetLocaleForTests();
  window.localStorage.clear();
  clearUiToken();
});

describe("FXTESTSUI row a: view key, route path, tab entry", () => {
  it("registers the tests view key with a project menu entry", () => {
    expect(PROJECT_VIEWS).toContain("tests");
    expect(projectMenuTestId("tests")).toBe("project-menu-tests");
  });

  it("mounts the Tests tab at the shipped tests route path", async () => {
    expect(TESTS_ROUTE_PATH).toBe("/projects/:projectId/tests");
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <MemoryRouter initialEntries={["/projects/p-7/tests"]}>
          <Routes>
            <Route
              path={TESTS_ROUTE_PATH}
              element={<ProjectView projectId="p-7" view="tests" />}
            />
          </Routes>
        </MemoryRouter>,
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("project-menu-tests")).toBeTruthy();
    expect(await screen.findByTestId("tests-tab")).toBeTruthy();
    expect(await screen.findByTestId("tests-row-t-boot")).toBeTruthy();
  });
});

describe("FXTESTSUI row b: TestsTab counters, rows, output, empty, refresh", () => {
  it("renders served counters and per-test rows from faked fetch only", async () => {
    render(<TestsTab projectId="p-7" />);
    expect((await screen.findByTestId("tests-counters-active")).textContent).toBe(
      "2",
    );
    expect((await screen.findByTestId("tests-counters-passed")).textContent).toBe(
      "1",
    );
    expect(
      (await screen.findByTestId("tests-counters-remaining")).textContent,
    ).toBe("1");
    expect((await screen.findByTestId("tests-name-t-boot")).textContent).toBe(
      "t-boot",
    );
    expect((await screen.findByTestId("tests-kind-t-boot")).textContent).toBe(
      "code",
    );
    expect((await screen.findByTestId("tests-status-t-boot")).textContent).toBe(
      "PASS",
    );
    expect((await screen.findByTestId("tests-kind-t-chat")).textContent).toBe(
      "AI",
    );
    expect((await screen.findByTestId("tests-status-t-chat")).textContent).toBe(
      "BLOCKED",
    );
    expect((await screen.findByTestId("tests-reason-t-chat")).textContent).toBe(
      "needs chat provider",
    );
    expect(screen.queryByTestId("tests-reason-t-boot")).toBeNull();
    const reads = seen.filter((request) => request.method === "GET");
    expect(reads.length).toBeGreaterThan(0);
    for (const request of reads) {
      expect(request.headers["x-ui-session-token"] ?? "").toBe("");
      expect(request.url).not.toContain("token");
    }
    expect(
      (await screen.findByTestId("tests-explainer")).textContent ?? "",
    ).toContain("local tests");
  });

  it("opens the served output text on click", async () => {
    render(<TestsTab projectId="p-7" />);
    fireEvent.click(await screen.findByTestId("tests-output-t-boot"));
    expect(
      (await screen.findByTestId("tests-output-text-t-boot")).textContent,
    ).toContain("boot ok");
    expect(screen.queryByTestId("tests-output-t-chat")).toBeNull();
  });

  it("shows an empty state naming how a run starts when no run exists", async () => {
    render(<TestsTab projectId="p-empty" />);
    expect(await screen.findByTestId("tests-empty")).toBeTruthy();
    // FXOPEN O5: plain words, never the raw route.
    const how =
      (await screen.findByTestId("tests-empty-how")).textContent ?? "";
    expect(how).toContain("Start a run for the latest plan");
    expect(how).not.toMatch(/[A-Za-z]:[\\/]|\/api\//);
  });

  it("holds no setting control", async () => {
    const view = render(<TestsTab projectId="p-7" />);
    await screen.findByTestId("tests-row-t-boot");
    expect(
      view.container.querySelectorAll("input,select,textarea").length,
    ).toBe(0);
    expect(screen.queryByTestId("local-tests-switch")).toBeNull();
    view.unmount();
  });

  it("refreshes the view while the run is unfinished and stops when done", async () => {
    vi.useFakeTimers();
    render(<TestsTab projectId="p-7" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(screen.getByTestId("tests-row-t-boot")).toBeTruthy();
    expect(testsViewCalls).toBe(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(testsViewCalls).toBe(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(testsViewCalls).toBe(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(testsViewCalls).toBe(3);
  });
});

describe("FXTESTSUI row c: ONE local-tests switch with token POST and read-back", () => {
  it("defaults to the GET answer, posts once with the session token, reads back", async () => {
    setUiToken(TOKEN);
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectView projectId="p-9" view="overview" />
      </ApiClientProvider>,
    );
    const toggle = (await screen.findByTestId(
      "local-tests-switch",
    )) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(
        (screen.getByTestId("local-tests-value").textContent ?? ""),
      ).toBe("off");
    });
    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/teststage/local-tests" &&
        request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(posts[0]?.url).not.toContain("token");
    expect(posts[0]?.body ?? "").not.toContain("session_token");
    expect(posts[0]?.body ?? "").toContain('"enabled":false');
    const gets = seen.filter(
      (request) =>
        request.url === "/api/v1/teststage/local-tests?project_id=p-9" &&
        request.method === "GET",
    );
    expect(gets.length).toBeGreaterThanOrEqual(2);
    expect(
      document.querySelectorAll('[data-testid="local-tests-switch"]').length,
    ).toBe(1);
  });
});
