/** @vitest-environment jsdom */
// FXDESIGN1 styling + labels lane (S1-S5): the real App renders the project
// NAME (never the id) in the topbar select with a locale placeholder when
// no project is open; team rows show labelled fields with the role in plain
// locale words (never a raw enum, uiRole or manager literal) and long refs
// truncated behind a title; the stop status is short plain text.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import type { PartRow } from "../../api/iface";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = { project_id: "p-9", name: "Design Proj", created_at: "t-0" };

const LONG_FILE = "src/some/very/long/nested/path/to/module/file.ts";

function liveRows(): PartRow[] {
  const rows = [
    {
      agent: "agent-7",
      scope: "scope-7",
      deliverable: "part-7",
      status: "RUNNING",
      role: "manager",
      provider: "prov-7",
      model: "m-7",
      step: 3,
      file: LONG_FILE,
      last_action: "edited a very long action reference text",
      silent_min: 5,
      waits: ["agent-8"],
      uiRole: "manager",
    },
  ];
  return rows as unknown as PartRow[];
}

function renderApp(client: FakeApiClient, route = "/"): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxdesign1 topbar select", () => {
  it("shows the project NAME and never the id", async () => {
    renderApp(new FakeApiClient({ projects: [PROJECT], liveRows: liveRows() }));
    const select = (await screen.findByTestId(
      "topbar-project",
    )) as HTMLSelectElement;
    expect(select.textContent).toContain("Design Proj");
    expect(select.textContent).not.toContain("p-9");
  });

  it("offers a locale placeholder option when no project is open", async () => {
    renderApp(new FakeApiClient({ projects: [], liveRows: [] }));
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const select = screen.getByTestId(
      "topbar-project",
    ) as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option"));
    expect(options.length).toBeGreaterThan(0);
    expect(select.textContent).toContain(t("shell.topbar.projectPlaceholder"));
  });
});

describe("fxdesign1 team rows", () => {
  it("labels fields with the role in plain locale words, truncating refs", async () => {
    renderApp(new FakeApiClient({ projects: [PROJECT], liveRows: liveRows() }));
    const row = await screen.findByTestId("team-row-agent-7");
    const text = row.textContent ?? "";
    expect(text).toContain(t("providers.role.manager"));
    expect(text).not.toContain("manager");
    expect(text).not.toContain("uiRole");
    expect(row.querySelector(`[title="${LONG_FILE}"]`)).toBeTruthy();
  });
});

describe("fxdesign1 stop status", () => {
  it("renders the stop result as short plain status text", async () => {
    vi.stubGlobal(
      "fetch",
      async (input: unknown) =>
        new Response(JSON.stringify({ ok: true }), {
          status: String(input) === "/api/v1/stop-all" ? 200 : 404,
          headers: { "content-type": "application/json" },
        }),
    );
    renderApp(new FakeApiClient({ projects: [PROJECT], liveRows: liveRows() }));
    fireEvent.click(await screen.findByTestId("topbar-stop-all"));
    fireEvent.click(screen.getByTestId("topbar-stop-all"));
    expect((await screen.findByTestId("stop-all-result")).textContent).toBe(
      "200",
    );
  });
});
