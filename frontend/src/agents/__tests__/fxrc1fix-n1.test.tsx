/** @vitest-environment jsdom */
// FXRC1FIX N1: AgentsLive shows only live rows. Ended rows from older
// runs (RETURNED/ACCEPTED/REJECTED/BLOCKED) drop out; QUEUED/RUNNING/
// HANDOFF stay visible with their state.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
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

const MIXED_ROWS = [
  { agent: "live-run", scope: "s-run", deliverable: "d-run", status: "RUNNING" },
  { agent: "live-queue", scope: "s-queue", deliverable: "d-queue", status: "QUEUED" },
  { agent: "live-hold", scope: "s-hold", deliverable: "d-hold", status: "HANDOFF" },
  { agent: "gone-returned", scope: "s-ret", deliverable: "d-ret", status: "RETURNED" },
  { agent: "gone-accepted", scope: "s-acc", deliverable: "d-acc", status: "ACCEPTED" },
  { agent: "gone-rejected", scope: "s-rej", deliverable: "d-rej", status: "REJECTED" },
  { agent: "gone-blocked", scope: "s-blo", deliverable: "d-blo", status: "BLOCKED" },
] as const;

describe("fxrc1fix N1 agents live ended rows", () => {
  it("drops ended rows and keeps live ones with exact counts", async () => {
    const client = new FakeApiClient({
      liveRows: MIXED_ROWS.map((row) => ({ ...row })),
    });
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-live-run")).toBeTruthy();
    expect(await screen.findByTestId("agent-row-live-queue")).toBeTruthy();
    expect(await screen.findByTestId("agent-row-live-hold")).toBeTruthy();
    for (const agent of [
      "gone-returned",
      "gone-accepted",
      "gone-rejected",
      "gone-blocked",
    ]) {
      expect(screen.queryByTestId(`agent-row-${agent}`)).toBeNull();
    }
    expect(
      (await screen.findByTestId("agent-badge-UNKNOWN")).textContent,
    ).toContain("3");
  });

  it("shows the empty state when every row ended", async () => {
    const client = new FakeApiClient({
      liveRows: MIXED_ROWS.filter((row) =>
        ["RETURNED", "ACCEPTED", "REJECTED", "BLOCKED"].includes(row.status),
      ).map((row) => ({ ...row })),
    });
    // FXLOOK D5: the empty line links at Chat, so it renders under a
    // Router (the live branch above needs none).
    render(
      <MemoryRouter initialEntries={["/agents/live"]}>
        <ApiClientProvider client={client}>
          <AgentsLive projectId="p-1" />
        </ApiClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("kit-card-agents-live")).toBeTruthy();
    expect(screen.queryByTestId("agents-live-rows")).toBeNull();
  });
});
