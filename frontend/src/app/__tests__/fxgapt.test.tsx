/** @vitest-environment jsdom */
// FXGAPT real-page proofs for the INT_GATE G5 gaps: every test renders
// the REAL App at its REAL route; only global fetch is faked (quoting
// the served schemas). Row ids F01/F02/F05/F14 appear literally so the
// G5 probe maps them; F06/P16 ride the same file (F06 GREEN here, P16
// GREEN-feature plus a RED row-testic mismatch).
//
// RED tests (test_red_*) fail by design: each proves one product defect
// at entry -> observable-result level. The fix lane turns them GREEN;
// no product file is touched here.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { App } from "../App";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";

const PROJECT = {
  project_id: "p1",
  name: "P1",
  created_at: "2026-01-01T00:00:00Z",
};

const BUDGET = {
  project_id: "p1",
  budget: {
    project_id: "p1",
    hard_limit: 100,
    spent: 10,
    reserved: 5,
    currency: "USD",
  },
};

interface SeenRequest {
  url: string;
  method: string;
  body: string | null;
}

let seen: SeenRequest[] = [];
let liveAgents: unknown[] = [];
let connectedProviders: unknown[] = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubBoundary(): void {
  seen = [];
  liveAgents = [];
  connectedProviders = [{ provider_id: "meta" }];
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const body =
        typeof init?.body === "string" ? (init.body as string) : null;
      seen.push({ url, method, body });
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/tasks?project_id=p1") {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url === "/api/v1/runs/ledger?project_id=p1") {
        return jsonBody({ rows: [] });
      }
      if (method === "GET" && url === "/api/v1/budget?project_id=p1") {
        return jsonBody(BUDGET);
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: liveAgents });
      }
      if (method === "GET" && url === "/api/v1/providers") {
        return jsonBody({ providers: connectedProviders });
      }
      if (
        method === "GET" &&
        url === "/api/v1/teststage/local-tests?project_id=p1"
      ) {
        return jsonBody({ project_id: "p1", enabled: true });
      }
      if (
        method === "GET" &&
        url === "/api/v1/teststage/plans/latest?project_id=p1"
      ) {
        return jsonBody({ project_id: "p1", plan_id: "plan-1" });
      }
      if (
        method === "GET" &&
        url === "/api/v1/teststage/runs/latest?project_id=p1"
      ) {
        return jsonBody({
          project_id: "p1",
          plan_id: "plan-1",
          run_id: "run-1",
        });
      }
      if (
        method === "GET" &&
        url === "/api/v1/teststage/tests-view?plan_id=plan-1&run_id=run-1"
      ) {
        return jsonBody({
          plan_id: "plan-1",
          run_id: "run-1",
          active: 2,
          passed: 2,
          remaining: 0,
          rows: [
            {
              test_id: "t-boot",
              status: "PASS",
              output_ref: "evidence://p1/out-1",
              kind: "CODE",
            },
            {
              test_id: "t-chat",
              status: "PASS",
              output_ref: null,
              kind: "AI",
            },
          ],
          settings_controls: [],
        });
      }
      if (
        method === "GET" &&
        url ===
          "/api/v1/teststage/result-output?ref=" +
            encodeURIComponent("evidence://p1/out-1")
      ) {
        return jsonBody({
          ref: "evidence://p1/out-1",
          project_id: "p1",
          output: "boot ok",
          size: 7,
        });
      }
      if (
        method === "GET" &&
        url === "/api/v1/routing/role?project_id=p1&role=manager"
      ) {
        return jsonBody({ code: "CONTEXT_MISSING" }, 404);
      }
      if (method === "PUT" && url === "/api/v1/routing/role") {
        const parsed =
          body === null ? {} : (JSON.parse(body) as Record<string, unknown>);
        return jsonBody({
          ok: true,
          profile: {
            role: "manager",
            project_id: "p1",
            mode: parsed["mode"] ?? "AUTO",
            provider: parsed["provider"] ?? null,
            model: parsed["model"] ?? null,
            binding: "DEFAULT",
            version: 1,
          },
        });
      }
      if (
        method === "GET" &&
        url === "/api/v1/watcher/status?project_id=p1"
      ) {
        return jsonBody({
          project_id: "p1",
          integrity_ok: true,
          journal_head: "evt-0007",
          generated_at: "2026-10-27T00:00:00Z",
        });
      }
      if (
        method === "GET" &&
        url === "/api/v1/watcher/journal?project_id=p1"
      ) {
        return jsonBody([
          { entry_id: "evt-0007", timestamp: "2026-10-27T00:00:00Z", hash: "h7" },
        ]);
      }
      if (method === "GET" && url === "/api/v1/kb/status") {
        return jsonBody({ kb_id: null });
      }
      return jsonBody({ code: "FXGAPT_UNEXPECTED_API" }, 404);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  stubBoundary();
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

function putsTo(url: string): SeenRequest[] {
  return seen.filter((entry) => entry.url === url && entry.method === "PUT");
}

async function openProject(): Promise<void> {
  fireEvent.click(screen.getByTestId("menu-projects"));
  expect(await screen.findByTestId("project-row-p1")).toBeTruthy();
  fireEvent.click(screen.getByTestId("project-open-p1"));
}

describe("fxgapt F01 tests tab on the real page", () => {
  it("opens the Tests tab from the project menu with counters and explainer", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await openProject();
    // FXLOOK D8: the chat route carries no tab strip, so the Tests tab
    // opens through Project details on the Overview data view.
    fireEvent.click(await screen.findByTestId("project-details-open"));
    fireEvent.click(await screen.findByTestId("project-menu-tests"));
    expect(await screen.findByTestId("tests-tab")).toBeTruthy();
    expect(await screen.findByTestId("tests-counters")).toBeTruthy();
    expect(
      (await screen.findByTestId("tests-counters-active")).textContent,
    ).toBe("2");
    expect(
      (await screen.findByTestId("tests-counters-passed")).textContent,
    ).toBe("2");
    expect(
      (await screen.findByTestId("tests-counters-remaining")).textContent,
    ).toBe("0");
    const explainer = await screen.findByTestId("tests-explainer");
    expect((explainer.textContent ?? "").length).toBeGreaterThan(0);
  });
});

describe("fxgapt F02 pinned binding on the real page", () => {
  it("pins provider+model through the editor and posts the saved binding", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.change(screen.getByTestId("topbar-project"), {
      target: { value: "p1" },
    });
    fireEvent.click(screen.getByTestId("menu-settings"));
    fireEvent.click(await screen.findByTestId("settings-link-project"));
    const modeLabel = t("settings.roleProfile.modeLabel");
    const providerLabel = t("settings.roleProfile.providerLabel");
    const modelLabel = t("settings.roleProfile.modelLabel");
    const needBoth = t("settings.validation.pinnedBindingRequired");
    const mode = (await screen.findByLabelText(modeLabel)) as HTMLSelectElement;
    // PINNED first with nothing set: the editor names the requirement.
    fireEvent.change(mode, { target: { value: "PINNED" } });
    await waitFor(() => {
      expect(screen.getByText(needBoth)).toBeTruthy();
    });
    fireEvent.change(await screen.findByLabelText(providerLabel), {
      target: { value: "meta" },
    });
    fireEvent.change(await screen.findByLabelText(modelLabel), {
      target: { value: "meta/muse-spark-1.3-contributor" },
    });
    await waitFor(() => {
      expect(screen.queryByText(needBoth)).toBeNull();
    });
    const puts = putsTo("/api/v1/routing/role");
    expect(puts.length).toBeGreaterThan(0);
    const last = JSON.parse(puts[puts.length - 1]?.body ?? "{}") as Record<
      string,
      unknown
    >;
    expect(last).toEqual({
      project_id: "p1",
      role: "manager",
      mode: "PINNED",
      provider: "meta",
      model: "meta/muse-spark-1.3-contributor",
    });
  });
});

describe("fxgapt F05 agents live on the real page", () => {
  it("renders the honest empty state with no run (empty is FAIL, never a pass)", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("team-open-agents"));
    expect(await screen.findByTestId("kit-empty-state")).toBeTruthy();
    expect(screen.queryByTestId("agents-live-rows")).toBeNull();
    expect(screen.queryByTestId("agent-row-live-1")).toBeNull();
  });

  it("renders the live row with scope while the run streams", async () => {
    liveAgents = [
      {
        agent: "live-1",
        scope: "task-fxgapt/run-1",
        deliverable: "artifact://run/r1/output",
        status: "RUNNING",
        role: "manager",
        model: "meta/muse-spark-1.3-contributor",
        step: 1,
        file: "",
        cost: "UNAVAILABLE",
        tokens: { input: 3, output: 5 },
        context: "artifact:run/r1/input",
        errors: [],
        waits: [],
        provider: "meta",
        placement: "CLOUD",
      },
    ];
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("team-open-agents"));
    expect(await screen.findByTestId("agents-live-rows")).toBeTruthy();
    expect(await screen.findByTestId("agent-row-live-1")).toBeTruthy();
    expect(screen.getByText(t("agents.row.scope"))).toBeTruthy();
  });
});

describe("fxgapt F06 watcher tab on the real page", () => {
  it("opens the watcher tab with project, integrity and per-card models", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.change(screen.getByTestId("topbar-project"), {
      target: { value: "p1" },
    });
    // FXFACTS F15: the top bar carries no watcher link; the rail Watcher
    // card holds the Open link.
    fireEvent.click(await screen.findByTestId("rail-toggle-watcher"));
    fireEvent.click(await screen.findByTestId("watcher-open"));
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(screen.getByTestId("watcher-project").textContent).toBe("p1");
    expect(await screen.findByTestId("watcher-rule-cards")).toBeTruthy();
    for (const card of ["card-hang", "card-guard", "card-tamper"]) {
      expect(await screen.findByTestId(`rule-card-${card}`)).toBeTruthy();
      const model = screen.getByTestId(`rule-card-${card}-model`);
      expect((model.textContent ?? "").length).toBeGreaterThan(0);
    }
  });
});

describe("fxgapt F14 first run on the real page", () => {
  it("lands a fresh profile on /firstrun by itself", async () => {
    connectedProviders = [];
    vi.stubGlobal(
      "fetch",
      async (input: unknown, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        seen.push({ url, method, body: null });
        if (method === "GET" && url === "/api/v1/providers") {
          return jsonBody({ providers: [] });
        }
        if (method === "GET" && url === "/api/v1/projects") {
          return jsonBody({ projects: [] });
        }
        return jsonBody({ code: "FXGAPT_UNEXPECTED_API" }, 404);
      },
    );
    renderAppAt("/");
    expect(await screen.findByText(t("firstrun.title"))).toBeTruthy();
    expect(await screen.findByText(t("firstrun.next"))).toBeTruthy();
  });
});

describe("fxgapt P16 how-it-works on the real page", () => {
  it("renders the diagram with six chained stages and the plain-words concepts", async () => {
    renderAppAt("/how-it-works");
    const diagram = await screen.findByTestId("how-it-works-diagram");
    expect(diagram.tagName.toLowerCase()).toBe("svg");
    const stages = within(diagram as unknown as HTMLElement).getAllByTestId(
      /how-it-works-stage-/,
    );
    expect(stages).toHaveLength(6);
    const concepts = await screen.findByTestId("how-it-works-concepts");
    expect(concepts.textContent).toContain(t("howItWorks.runs.body"));
    expect(concepts.textContent).toContain(t("howItWorks.codeTests.body"));
    expect(concepts.textContent).toContain(t("howItWorks.localTests.body"));
  });

  it("p16 row testid alignment: the live row waits on how-it-works-diagram", async () => {
    // Was RED: rows.json P16-howitworks waited on testid
    // kit-card-howitworks-diagram while the product rendered
    // how-it-works-diagram. The row is fixed on int (waits on
    // how-it-works-diagram now), so this asserts the aligned
    // expectation: the diagram the row waits on is mounted.
    renderAppAt("/how-it-works");
    expect(await screen.findByTestId("how-it-works-diagram")).toBeTruthy();
  });
});

describe("fxgapt laptop-B chrome on the real page", () => {
  it("test_red_laptop_stop_all: Stop-all arms only while a run is live", async () => {
    // RED: topbar-stop-all is always enabled, even with no run
    // (agents/live []). Photo 02: red Stop-all while the rail says
    // "No agents running". Expected: disabled/absent when idle.
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("team-open-agents"));
    expect(await screen.findByTestId("kit-empty-state")).toBeTruthy();
    const stop = screen.getByTestId("topbar-stop-all") as HTMLButtonElement;
    expect(stop.disabled).toBe(true);
  });

  it("test_red_laptop_uk_chrome: Ukrainian UI names the theme in Ukrainian", async () => {
    // RED: with locale uk the header reads "Оформлення: dark" — the
    // label is localized, the value is a raw English token
    // (ThemeToggle.tsx). Photo 18. Expected: "Оформлення: темна".
    setLocale("uk");
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const toggle = await screen.findByTestId("theme-toggle");
    const text = toggle.textContent ?? "";
    expect(text).not.toContain("dark");
    expect(text).not.toContain("light");
  });
});
