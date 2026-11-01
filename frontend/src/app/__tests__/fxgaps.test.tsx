/** @vitest-environment jsdom */
// FXGAPS F06/F09/F11/F12: the REAL App mounts every gap control at its
// route; only global fetch is replaced (quoting the served schemas).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../ApiClientProvider";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../App";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const BUDGET = {
  project_id: "p-1",
  budget: {
    project_id: "p-1",
    hard_limit: 100,
    spent: 10,
    reserved: 5,
    currency: "u-1",
  },
};

const SEEN: Array<{ url: string; method: string; body: string }> = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function serve(data: unknown): Response {
  return jsonBody(data);
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  SEEN.length = 0;
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: unknown }) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      let body = "";
      try {
        body =
          typeof init?.body === "string"
            ? (init.body as string)
            : JSON.stringify(init?.body ?? "");
      } catch {
        body = "";
      }
      SEEN.push({ url, method, body });
      if (url === "/api/v1/projects") {
        return serve({ projects: [PROJECT] });
      }
      if (url === "/api/v1/projects/p-1") {
        return serve({ project: PROJECT });
      }
      if (url === "/api/v1/tasks?project_id=p-1") {
        return serve({ tasks: [] });
      }
      if (url === "/api/v1/runs/ledger?project_id=p-1") {
        return serve({ rows: [] });
      }
      if (url === "/api/v1/agents/live") {
        return serve({ agents: [] });
      }
      if (url === "/api/v1/budget?project_id=p-1") {
        return serve(BUDGET);
      }
      if (url === "/api/v1/watcher/status?project_id=p-1") {
        return serve({
          project_id: "p-1",
          integrity_ok: true,
          journal_head: "evt-0007",
          generated_at: "2026-10-27T00:00:00Z",
        });
      }
      if (url === "/api/v1/watcher/journal?project_id=p-1") {
        return serve([
          {
            entry_id: "evt-0007",
            timestamp: "2026-10-27T00:00:00Z",
            hash: "h7",
          },
        ]);
      }
      if (url === "/api/v1/kb/status") {
        return serve({
          overall: { last_update: "2026-10-27T00:00:00Z" },
          per_provider: { prov: "2026-10-26T00:00:00Z" },
        });
      }
      if (url === "/api/v1/kb/refresh/proposal") {
        return serve({
          kb_id: "kb-1",
          stale: true,
          proposals: [{ field: "price" }],
        });
      }
      if (url === "/api/v1/kb/update" && method === "POST") {
        return serve({
          applied: true,
          proposal_id: "kb-prop-1",
          kb_version: 8,
        });
      }
      if (url === "/api/v1/kb/proposals/apply" && method === "POST") {
        return serve({
          proposal_id: "kb-prop-1",
          applied: 5,
          version: { kb_version: 8 },
          cost_state: "ok",
          metric: "measured",
        });
      }
      if (url === "/api/v1/kb/attach" && method === "POST") {
        return serve("kb-p-1");
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
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

function postedTo(url: string): Array<{ url: string; method: string; body: string }> {
  return SEEN.filter((entry) => entry.url === url && entry.method === "POST");
}

describe("fxgaps F06 watcher control", () => {
  it("opens the watcher tab from the TopBar label and fetches status", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("topbar-watcher"));
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(screen.getByTestId("watcher-project").textContent).toBe("p-1");
    expect(
      SEEN.some(
        (entry) => entry.url === "/api/v1/watcher/status?project_id=p-1",
      ),
    ).toBe(true);
  });

  it("opens the watcher tab from the TopBar link while the sidebar keeps four entries", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const sidebar = screen.getByTestId("sidebar");
    const anchors = Array.from(sidebar.querySelectorAll("a"));
    expect(
      anchors.map((anchor) => anchor.getAttribute("data-testid")).sort(),
    ).toEqual(
      ["menu-new-task", "menu-projects", "menu-results", "menu-settings"].sort(),
    );
    expect(screen.queryByTestId("menu-watcher")).toBeNull();
    fireEvent.click(screen.getByTestId("topbar-watcher"));
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
  });
});

describe("fxgaps F09 capability database model KB", () => {
  it("shows KB status, runs refresh plus apply, and hides ProvidersPage", async () => {
    renderAppAt("/settings/capabilityDB");
    expect(await screen.findByTestId("kb-status")).toBeTruthy();
    expect(screen.getByTestId("kb-status").textContent).toContain("overall");
    fireEvent.click(await screen.findByTestId("kb-update"));
    expect(await screen.findByTestId("kb-update-result")).toBeTruthy();
    expect(screen.getByTestId("kb-update-result").textContent).toContain(
      "kb-prop-1",
    );
    expect(postedTo("/api/v1/kb/update")).toHaveLength(1);
    expect(postedTo("/api/v1/kb/proposals/apply")).toHaveLength(1);
    expect(
      JSON.parse(postedTo("/api/v1/kb/update")[0]?.body ?? "{}"),
    ).toEqual({ approved_by_user: true });
    expect(screen.queryByTestId("provider-card")).toBeNull();
    expect(await screen.findByTestId("k07next2-kb-proposal")).toBeTruthy();
  });
});

describe("fxgaps F11 KB attach in project context", () => {
  it("posts the project source and lists the attached answer", async () => {
    renderAppAt("/projects/p-1/overview");
    expect(await screen.findByTestId("overview-name")).toBeTruthy();
    expect(await screen.findByTestId("kb-attach-control")).toBeTruthy();
    fireEvent.change(screen.getByTestId("kb-attach-kb-id"), {
      target: { value: "kb-p-1" },
    });
    fireEvent.change(screen.getByTestId("kb-attach-purpose"), {
      target: { value: "project notes" },
    });
    fireEvent.click(screen.getByTestId("kb-attach-submit"));
    expect(await screen.findByTestId("kb-attach-result")).toBeTruthy();
    expect(screen.getByTestId("kb-attach-list").textContent).toContain(
      "kb-p-1",
    );
    const posts = postedTo("/api/v1/kb/attach");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0]?.body ?? "{}")).toEqual({
      source: {
        kb_id: "kb-p-1",
        kind: "DEV_ROLE",
        project_id: "p-1",
        role: null,
        purpose: "project notes",
      },
    });
  });
});

describe("fxgaps F12 project tokens from served budget", () => {
  it("shows spend and limits from the budget answer", async () => {
    renderAppAt("/projects/p-1/tokens");
    expect(await screen.findByTestId("tokens-spent")).toBeTruthy();
    expect(screen.getByTestId("tokens-spent").textContent).toContain("10");
    expect(screen.getByTestId("tokens-limit").textContent).toContain("100");
    expect(
      SEEN.some(
        (entry) => entry.url === "/api/v1/budget?project_id=p-1",
      ),
    ).toBe(true);
    expect(screen.queryByText(t("ui.table.empty"))).toBeNull();
  });
});
