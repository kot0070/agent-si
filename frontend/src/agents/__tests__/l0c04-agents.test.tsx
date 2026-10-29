/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { AgentsLive } from "../AgentsLive";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("L0C-04 inspector shows the project name, never the raw id", () => {
  it("renders the served project name for a known id", async () => {
    const client = new FakeApiClient({
      liveRows: [],
      projects: [
        { project_id: "proj-raw-123", name: "Alpha Project", created_at: "t-0" },
      ],
    });
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="proj-raw-123" />
      </ApiClientProvider>,
    );
    const label = await screen.findByTestId("agents-live-project");
    expect(label.textContent).toBe("Alpha Project");
    expect(label.textContent).not.toContain("proj-raw-123");
  });

  it("falls back to the project label, never the raw id, when unknown", async () => {
    const client = new FakeApiClient({
      liveRows: [],
      projects: [
        { project_id: "p-1", name: "n-1", created_at: "t-0" },
      ],
    });
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="missing-raw-999" />
      </ApiClientProvider>,
    );
    const label = await screen.findByTestId("agents-live-project");
    expect(label.textContent).toBe(t("shell.topbar.project"));
    expect(label.textContent).not.toContain("missing-raw-999");
  });
});
