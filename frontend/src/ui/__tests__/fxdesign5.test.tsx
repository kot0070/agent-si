/** @vitest-environment jsdom */
// FXDESIGN5 S1-S7: Claude-desktop polish bar over the REAL App (only global
// fetch is faked; served shapes quoted from src/agent_si/backend/*) plus
// unit renders over FakeApiClient. RED before the fix, GREEN after.
// S1 shell fills the viewport incl. a below-1200px drawer rule with no
// page sideways scroll; rails scroll only on overflow with token
// scrollbars. S2 chat fills the centre column
// (max-width 900px) with an in-flow composer (normal flow, after messages,
// never sticky/fixed/absolute/overlapping) and no inline overlay override. S3 one thin top strip: project dropdown first, right group
// after, every control named. S4 one primary per form/card: quiet
// secondaries. S5 exactly one active rail entry per route. S6 served
// UNKNOWN evidence renders the locale label; empty states carry only the
// locale empty text. S7 every option control in the owned regions is named.
// @ts-ignore: node builtin types are not installed in this workspace; vitest resolves "fs" at runtime.
import { readFileSync } from "fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import type { PartRow } from "../../api/iface";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";
import { AgentsLive } from "../../agents/AgentsLive";
import { ApprovalCard } from "../../chat/ApprovalCard";
import en from "../../locale/en.json";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const SHELL_CSS = readFileSync("src/ui/shell.css", "utf8");

function asRow(extra: Record<string, unknown>): PartRow {
  return extra as unknown as PartRow;
}

const UNKNOWN_ROW = asRow({
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

function named(control: Element): boolean {
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

describe("fxdesign5 S1 shell fills the viewport without overlap", () => {
  it("ships the viewport-height, overflow-only and token scrollbar rules with all regions", async () => {
    expect(SHELL_CSS).toContain("height: 100vh");
    expect(SHELL_CSS).toContain("min-height: 100vh");
    expect(SHELL_CSS).toContain("overflow-y: auto");
    expect(SHELL_CSS).not.toMatch(/overflow-y:\s*scroll/);
    expect(SHELL_CSS).toContain("scrollbar-color");
    expect(SHELL_CSS).toContain("scrollbar-width");
    renderAppAt("/projects");
    const shell = await screen.findByTestId("app-shell");
    for (const region of ["topbar", "sidebar", "app-main", "inspector"]) {
      expect(within(shell).getByTestId(region)).toBeTruthy();
    }
  });

  it("opens the rail as an overlay drawer below 1200px with no page sideways scroll", () => {
    // FXFACTS F8: below 1200px the rail is an overlay drawer, never a
    // squeezed column; the main column takes the full width.
    expect(SHELL_CSS).toMatch(/max-width:\s*1199px/);
    const narrow = SHELL_CSS.split("@media (max-width: 1199px)")[1] ?? "";
    expect(narrow).toMatch(/minmax\(0,\s*1fr\)/);
    expect(narrow).toMatch(/position:\s*fixed/);
    expect(narrow).toMatch(/data-open/);
    expect(SHELL_CSS).toContain("overflow-x: clip");
  });
});

describe("fxdesign5 S2 chat fills the centre column up to 900px", () => {
  it("lists messages above an in-flow composer inside the width rule", async () => {
    // Ruled meaning (P3): composer in normal flow after chat-messages,
    // never sticky/fixed/absolute/overlapping. Supersedes the old
    // sticky+bottom:0 dock pin, which contradicts shell.css position:static.
    expect(SHELL_CSS).toMatch(/chat-area[^}]*max-width:\s*900px/);
    expect(SHELL_CSS).toMatch(/chat-layout[^}]*max-width:\s*900px/);
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

  it("carries no inline overlay override on the composer", async () => {
    renderAppAt("/");
    const composer = await screen.findByTestId("chat-composer");
    // Same language as P3: never sticky/fixed/absolute (in-flow, static ok).
    expect((composer as HTMLElement).style.position).not.toMatch(
      /sticky|fixed|absolute/,
    );
  });
});

describe("fxdesign5 S3 one thin top strip", () => {
  it("names the project dropdown and keeps dropdown-left, group-right order", async () => {
    renderAppAt("/");
    const topbar = await screen.findByTestId("topbar");
    expect(topbar.tagName.toLowerCase()).toBe("header");
    expect(topbar.classList.contains("fx-topbar")).toBe(true);
    const project = within(topbar).getByTestId("topbar-project");
    expect(project.getAttribute("aria-label")?.trim()).toBe(
      t("shell.topbar.project"),
    );
    const stop = within(topbar).getByTestId("topbar-stop-all");
    const language = within(topbar).getByTestId("topbar-language");
    expect(
      (project.compareDocumentPosition(stop) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
    expect(
      (stop.compareDocumentPosition(language) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
    for (const control of topbar.querySelectorAll("select")) {
      expect(named(control)).toBe(true);
    }
  });
});

describe("fxdesign5 S4 one primary per form and card", () => {
  it("keeps a single submit with quiet secondaries on the project form", async () => {
    renderAppAt("/projects");
    const form = await screen.findByTestId("project-add-form");
    expect(form.querySelectorAll('button[type="submit"]')).toHaveLength(1);
    expect(
      screen.getByTestId("project-add-submit").classList.contains("fx-btn-quiet"),
    ).toBe(false);
    expect(
      screen.getByTestId("project-folder-choose").classList.contains("fx-btn-quiet"),
    ).toBe(true);
  });

  it("keeps accept primary with quiet edit and reject on the approval card", () => {
    render(
      <ApprovalCard
        proposal="do it"
        onAccept={() => undefined}
        onEdit={() => undefined}
        onReject={() => undefined}
      />,
    );
    expect(
      screen.getByTestId("approval-accept").classList.contains("fx-btn-quiet"),
    ).toBe(false);
    expect(
      screen.getByTestId("approval-edit").classList.contains("fx-btn-quiet"),
    ).toBe(true);
    expect(
      screen.getByTestId("approval-reject").classList.contains("fx-btn-quiet"),
    ).toBe(true);
  });
});

describe("fxdesign5 S5 exactly one active rail entry", () => {
  it("marks only New task on the chat route", async () => {
    renderAppAt("/");
    const sidebar = await screen.findByTestId("sidebar");
    const current = sidebar.querySelectorAll('[aria-current="page"]');
    expect(current).toHaveLength(1);
    expect(screen.getByTestId("menu-new-task").getAttribute("aria-current")).toBe(
      "page",
    );
    expect(
      screen.getByTestId("menu-new-task").classList.contains("fx-nav-active"),
    ).toBe(true);
  });

  it("marks only Settings on the settings index", async () => {
    renderAppAt("/settings");
    const sidebar = await screen.findByTestId("sidebar");
    const current = sidebar.querySelectorAll('[aria-current="page"]');
    expect(current).toHaveLength(1);
    expect(screen.getByTestId("menu-settings").getAttribute("aria-current")).toBe(
      "page",
    );
  });
});

describe("fxdesign5 S6 served codes read as human labels with empty-only text", () => {
  it("labels an UNKNOWN placement through the locale on the live panel", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient({ liveRows: [UNKNOWN_ROW] })}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    const place = await screen.findByTestId("agent-row-place-bare-1");
    expect(place.textContent).toBe(en.shell.common.unknown);
    expect(place.textContent).not.toContain("UNKNOWN");
  });

  it("shows exactly the locale empty text with no glued counts", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient({ liveRows: [] })}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    const card = await screen.findByTestId("kit-card-agents-live");
    const empty = within(card).getByTestId("kit-empty-state");
    expect(empty.textContent).toBe(t("agents.live.empty"));
  });
});

describe("fxdesign5 S7 every option control in the owned regions is named", () => {
  it("names the topbar and chat prompt controls", async () => {
    renderAppAt("/");
    await screen.findByTestId("topbar");
    for (const testId of ["topbar-project", "topbar-language", "chat-prompt"]) {
      const control = screen.getByTestId(testId);
      expect(named(control)).toBe(true);
      expect(
        control.getAttribute("aria-label")?.trim() ||
          control.closest("label")?.textContent?.trim(),
      ).toBeTruthy();
    }
  });

  it("names the project form controls", async () => {
    renderAppAt("/projects");
    await screen.findByTestId("project-add-form");
    for (const testId of ["project-add-name", "project-add-folder"]) {
      expect(named(screen.getByTestId(testId))).toBe(true);
    }
  });
});
