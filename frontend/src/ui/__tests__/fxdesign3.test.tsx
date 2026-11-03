/** @vitest-environment jsdom */
// FXDESIGN3 S1-S7: the real App over a stubbed fetch (only global fetch is
// replaced; served shapes quoted from src/agent_si/backend/*). RED before
// the fix, GREEN after. S1 shell fills the viewport (min-height rule plus
// token scrollbar rules, regions present); S2 chat list fills the centre
// column with the composer in flow last (in-flow, after messages, never
// sticky/fixed/absolute/overlapping); S3 no Watcher word in the top bar
// (the rail Watcher card holds it, F15) while the card still navigates
// to /watcher; S4 one primary per form (folder-choose quiet) with the kit
// chevron intact;
// S5 the active rail entry exposes aria-current; S6 served UNKNOWN evidence
// renders the locale label, never the bare enum; S7 every option control in
// the owned regions is associated with its label.
// @ts-ignore: node builtin types are not installed in this workspace; vitest resolves "fs" at runtime.
import { readFileSync } from "fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";
import { LocalBenchTab } from "../../settings/LocalBenchTab";
import type { LocalBenchClient } from "../../settings/LocalBenchClient";
import type {
  LocalBenchEstimate,
  LocalBenchResultRow,
  LocalBenchRunRequest,
  LocalBenchScanResult,
} from "../../settings/LocalBenchTypes";
import { RolePoolPicker } from "../../settings/ProvidersPage/RolePoolPicker";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const SHELL_CSS = readFileSync("src/ui/shell.css", "utf8");
const BASE_CSS = readFileSync("src/ui/base.css", "utf8");

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: unknown }) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (url === "/api/v1/projects/p-1") {
        return jsonBody({ project: PROJECT });
      }
      if (url === "/api/v1/tasks?project_id=p-1") {
        return jsonBody({ tasks: [] });
      }
      if (url === "/api/v1/runs/ledger?project_id=p-1") {
        return jsonBody({ rows: [] });
      }
      if (url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (url === "/api/v1/budget?project_id=p-1") {
        return jsonBody({
          project_id: "p-1",
          budget: {
            project_id: "p-1",
            hard_limit: 100,
            spent: 10,
            reserved: 5,
            currency: "u-1",
          },
        });
      }
      if (url === "/api/v1/watcher/status?project_id=p-1") {
        return jsonBody({
          project_id: "p-1",
          integrity_ok: true,
          journal_head: "evt-0007",
          generated_at: "2026-10-27T00:00:00Z",
        });
      }
      if (url === "/api/v1/watcher/journal?project_id=p-1") {
        return jsonBody([
          { entry_id: "evt-0007", timestamp: "2026-10-27T00:00:00Z", hash: "h7" },
        ]);
      }
      if (url === "/api/v1/kb/status") {
        return jsonBody({
          overall: { kb_version: 3, evidence: "UNKNOWN" },
          per_provider: { prov: "2026-10-26T00:00:00Z" },
        });
      }
      if (url === "/api/v1/kb/refresh/proposal") {
        return jsonBody({ kb_id: "kb-1", stale: false, proposals: [] });
      }
      if (url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (url.startsWith("/api/v1/budget/providers/leftover-keys")) {
        return jsonBody({ entries: [] });
      }
      if (url.startsWith("/api/v1/chat/models")) {
        return jsonBody({ models: [] });
      }
      if (url === "/api/v1/kb/update" && method === "POST") {
        return jsonBody({ applied: true, proposal_id: "kb-prop-1", kb_version: 8 });
      }
      if (url === "/api/v1/kb/proposals/apply" && method === "POST") {
        return jsonBody({ proposal_id: "kb-prop-1", applied: 5 });
      }
      return jsonBody({}, 404);
    },
  );
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

function labelled(control: Element): boolean {
  if (control.getAttribute("aria-label")?.trim()) {
    return true;
  }
  if (control.getAttribute("aria-labelledby")?.trim()) {
    return true;
  }
  const id = control.getAttribute("id");
  if (id && document.querySelector(`label[for="${id}"]`) !== null) {
    return true;
  }
  const label = control.closest("label");
  return label !== null && (label.textContent ?? "").trim().length > 0;
}

describe("fxdesign3 S1 shell fills the viewport", () => {
  it("ships the viewport-height and token scrollbar rules with all regions", async () => {
    expect(SHELL_CSS).toContain("min-height: 100vh");
    expect(SHELL_CSS).toContain("scrollbar-color");
    expect(SHELL_CSS).toContain("scrollbar-width");
    expect(BASE_CSS).toContain("scrollbar-color");
    renderAppAt("/projects");
    const shell = await screen.findByTestId("app-shell");
    for (const region of ["topbar", "sidebar", "app-main", "inspector"]) {
      expect(within(shell).getByTestId(region)).toBeTruthy();
    }
  });
});

describe("fxdesign3 S2 chat fills the centre column", () => {
  it("lists messages above an in-flow composer with a width rule", async () => {
    // Ruled meaning (P3): composer in normal flow after chat-messages,
    // never sticky/fixed/absolute/overlapping. Supersedes the old
    // sticky+bottom:0 dock pin, which contradicts shell.css position:static.
    expect(SHELL_CSS).toMatch(/chat-composer[^}]*position:\s*static/);
    expect(SHELL_CSS).not.toMatch(
      /chat-composer[^}]*position:\s*(sticky|fixed|absolute)/,
    );
    expect(SHELL_CSS).toMatch(/chat-messages[^}]*overflow-y:\s*auto/);
    renderAppAt("/");
    const layout = await screen.findByTestId("chat-layout");
    const messages = within(layout).getByTestId("chat-messages");
    const composer = within(layout).getByTestId("chat-composer");
    expect(
      (messages.compareDocumentPosition(composer) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
  });
});

describe("fxdesign3 S3 single Watcher entry", () => {
  it("shows no Watcher string in the top bar; the rail card navigates", async () => {
    renderAppAt("/");
    const topbar = await screen.findByTestId("topbar");
    // FXFACTS F15: the watcher word lives in the rail Watcher card only.
    const hits = (topbar.textContent ?? "").match(/Watcher/g) ?? [];
    expect(hits).toEqual([]);
    expect(screen.queryByTestId("topbar-watcher")).toBeNull();
    expect(screen.queryByTestId("pairing-label")).toBeNull();
    fireEvent.click(await screen.findByTestId("rail-toggle-watcher"));
    fireEvent.click(await screen.findByTestId("watcher-open"));
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
  });
});

describe("fxdesign3 S4 one primary per form", () => {
  it("keeps a single submit with a quiet folder-choose and the kit chevron", async () => {
    renderAppAt("/projects");
    const form = await screen.findByTestId("project-add-form");
    const submits = form.querySelectorAll('button[type="submit"]');
    expect(submits.length).toBe(1);
    const choose = screen.getByTestId("project-folder-choose");
    expect(choose.classList.contains("fx-btn-quiet")).toBe(true);
    const toggle = screen.getByTestId("kit-toggle-projects-list");
    expect(toggle.classList.contains("fx-kit-toggle")).toBe(true);
    expect(toggle.getAttribute("aria-expanded")).not.toBeNull();
  });
});

describe("fxdesign3 S5 visible active rail entry", () => {
  it("marks the current rail entry with aria-current", async () => {
    renderAppAt("/");
    const fresh = await screen.findByTestId("menu-new-task");
    expect(fresh.getAttribute("aria-current")).toBe("page");
    for (const testId of ["menu-projects", "menu-results", "menu-settings"]) {
      expect(screen.getByTestId(testId).getAttribute("aria-current")).toBeNull();
    }
  });
});

describe("fxdesign3 S6 kb facts never show a bare enum", () => {
  it("labels served UNKNOWN evidence through the locale", async () => {
    renderAppAt("/settings/capabilityDB");
    const status = await screen.findByTestId("kb-status");
    expect(status.textContent).toContain("Unknown");
    expect(status.textContent).not.toContain("UNKNOWN");
    const empty = await screen.findByTestId("k07next2-kb-proposal-empty");
    expect(empty.textContent).toBe(t("ui.table.empty"));
  });

  it("labels served UNKNOWN evidence in the uk locale", async () => {
    setLocale("uk");
    renderAppAt("/settings/capabilityDB");
    const status = await screen.findByTestId("kb-status");
    expect(status.textContent).toContain("Невідомо");
    expect(status.textContent).not.toContain("UNKNOWN");
  });
});

describe("fxdesign3 S7 every option control has its label", () => {
  it("labels providers, role-pool and chat-model controls", async () => {
    // FXFACTS F7: provider cards live on models; role-pool and chat-model
    // controls live on routing. Both tabs keep every control labelled.
    renderAppAt("/settings/models");
    const cards = await screen.findAllByTestId("provider-card");
    expect(cards.length).toBeGreaterThan(0);
    const modelControls = Array.from(
      document.querySelectorAll('[data-testid="provider-card"] input'),
    );
    expect(modelControls.length).toBeGreaterThan(0);
    for (const control of modelControls) {
      expect(labelled(control)).toBe(true);
    }
    cleanup();
    renderAppAt("/settings/routing");
    const pageControls = Array.from(
      document.querySelectorAll(
        '[data-testid="role-pool-picker"] input, [data-testid="role-pool-picker"] select, [data-testid="chat-model-selector"] select',
      ),
    );
    expect(pageControls.length).toBeGreaterThan(0);
    for (const control of pageControls) {
      expect(labelled(control)).toBe(true);
    }
    const picker = document.querySelector('[data-testid="role-pool-picker"][data-role="manager"]');
    expect(picker).not.toBeNull();
    fireEvent.click(
      within(picker as HTMLElement).getByText(t("providers.rolepool.modePinned")),
    );
    const pinned = within(picker as HTMLElement)
      .getByText(t("providers.rolepool.pinnedAria", { role: "Manager" }))
      .closest("label");
    expect(pinned).not.toBeNull();
    fireEvent.click(
      within(picker as HTMLElement).getByText(t("providers.rolepool.modePool")),
    );
    const poolControls = Array.from(
      (picker as HTMLElement).querySelectorAll("input, select"),
    );
    expect(poolControls.length).toBeGreaterThan(0);
    for (const control of poolControls) {
      expect(labelled(control)).toBe(true);
    }
  });

  it("labels role-pool controls standalone", () => {
    render(
      <RolePoolPicker
        role="manager"
        project_id="p-1"
        options={[
          { key: "pool-opt-1", label: "Model One", providerId: "prov-a", modelId: "m-1" },
        ]}
        onChange={() => undefined}
      />,
    );
    const controls = Array.from(
      document.querySelectorAll('[data-testid="role-pool-picker"] input'),
    );
    expect(controls.length).toBeGreaterThan(0);
    for (const control of controls) {
      expect(labelled(control)).toBe(true);
    }
  });

  it("labels local-bench controls after a scan", async () => {
    const stub: LocalBenchClient = {
      scanModels: async (_path: string): Promise<LocalBenchScanResult> => ({
        path: _path,
        models: [{ model_id: "m-1", display_name: "Model One", evidence: "UNKNOWN" }],
      }),
      readEstimate: async (): Promise<LocalBenchEstimate> => ({
        model_id: "m-1",
        level: "quick",
        minutes_min: 1,
        minutes_max: 2,
      }),
      startRun: async (_request: LocalBenchRunRequest): Promise<string> => "run-1",
      pauseRun: async (): Promise<void> => undefined,
      resumeRun: async (): Promise<void> => undefined,
      stopRun: async (): Promise<void> => undefined,
      readResults: async (): Promise<LocalBenchResultRow[]> => [],
    };
    render(<LocalBenchTab client={stub} />);
    const path = screen.getByTestId("localbench-path");
    expect(labelled(path)).toBe(true);
    fireEvent.change(path, { target: { value: "bench-dir" } });
    fireEvent.click(screen.getByTestId("localbench-scan"));
    expect(await screen.findByTestId("localbench-model-m-1")).toBeTruthy();
    const tabControls = Array.from(
      document.querySelectorAll('[data-testid="localbench-tab"] input'),
    );
    expect(tabControls.length).toBeGreaterThan(0);
    for (const control of tabControls) {
      expect(labelled(control)).toBe(true);
    }
  });
});
