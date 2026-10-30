/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { AgentsLive } from "../AgentsLive";
import { resolveStatusHuman } from "../agentsApi";
import en from "../../locale/en.json";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

const THREE_ROWS = [
  { agent: "n-local", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
  { agent: "n-split", scope: "s-2", deliverable: "d-2", status: "HANDOFF" },
  { agent: "n-cloud", scope: "s-3", deliverable: "d-3", status: "QUEUED" },
] as const;

describe("agents live panel", () => {
  it("shows LOCAL plus SPLIT plus CLOUD badges with exact row counts", async () => {
    const client = new FakeApiClient({});
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-badge-LOCAL")).toBeTruthy();
    expect(await screen.findByTestId("agent-badge-SPLIT")).toBeTruthy();
    expect(await screen.findByTestId("agent-badge-CLOUD")).toBeTruthy();
    expect((await screen.findByTestId("agent-badge-LOCAL")).textContent).toContain("1");
    expect((await screen.findByTestId("agent-badge-CLOUD")).textContent).toContain("1");
    expect((await screen.findByTestId("agent-badge-SPLIT")).textContent).toContain("0");
  });

  it("shows a badge per node", async () => {
    const client = new FakeApiClient({
      liveRows: THREE_ROWS.map((row) => ({ ...row })),
    });
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-n-local")).toBeTruthy();
    expect(
      (await screen.findByTestId("agent-row-place-n-local")).textContent,
    ).toBe(en.agents.badge.local);
    expect(
      (await screen.findByTestId("agent-row-place-n-split")).textContent,
    ).toBe(en.agents.badge.split);
    expect(
      (await screen.findByTestId("agent-row-place-n-cloud")).textContent,
    ).toBe(en.agents.badge.cloud);
  });

  it("applies live rows without reload", async () => {
    const client = new FakeApiClient({});
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-agent-1")).toBeTruthy();
    const before = window.location.href;
    client.setLiveRows([
      { agent: "a-1", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
      { agent: "a-2", scope: "s-2", deliverable: "d-2", status: "QUEUED" },
    ]);
    expect(await screen.findByTestId("agent-row-a-2")).toBeTruthy();
    expect(window.location.href).toBe(before);
  });

  it("maps status codes and uk/en pairs to human text", () => {
    setLocale("en");
    expect(resolveStatusHuman(undefined, "RUNNING", "en")).toBe(
      en.tasks.status.running,
    );
    expect(
      resolveStatusHuman({ en: "pair-en", uk: "pair-uk" }, "QUEUED", "en"),
    ).toBe("pair-en");
    expect(
      resolveStatusHuman({ en: "pair-en", uk: "pair-uk" }, "QUEUED", "uk"),
    ).toBe("pair-uk");
    expect(t("tasks.status.handoff")).toBe(en.tasks.status.handoff);
  });

  it("shows the empty state when no agents run", async () => {
    const client = new FakeApiClient({ liveRows: [] });
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText(en.agents.live.empty)).toBeTruthy();
  });
});
