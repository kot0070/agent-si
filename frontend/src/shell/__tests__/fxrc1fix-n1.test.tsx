/** @vitest-environment jsdom */
// FXRC1FIX N1: Inspector Team-now shows only live rows. Ended rows from
// older runs (RETURNED/ACCEPTED/REJECTED/BLOCKED) drop out;
// QUEUED/RUNNING/HANDOFF stay visible with their state.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { ReactElement } from "react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { Inspector } from "../Inspector";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
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

function renderInspector(client: FakeApiClient): void {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <Inspector
            projectId="p-1"
            live={<span data-testid="live-probe">live content</span>}
          />
        ),
      },
    ],
    { initialEntries: ["/"] },
  );
  const node: ReactElement = (
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>
  );
  render(node);
}

describe("fxrc1fix N1 inspector team-now ended rows", () => {
  it("drops ended rows and keeps live ones", async () => {
    renderInspector(
      new FakeApiClient({ liveRows: MIXED_ROWS.map((row) => ({ ...row })) }),
    );
    expect(await screen.findByTestId("team-row-live-run")).toBeTruthy();
    expect(await screen.findByTestId("team-row-live-queue")).toBeTruthy();
    expect(await screen.findByTestId("team-row-live-hold")).toBeTruthy();
    for (const agent of [
      "gone-returned",
      "gone-accepted",
      "gone-rejected",
      "gone-blocked",
    ]) {
      expect(screen.queryByTestId(`team-row-${agent}`)).toBeNull();
    }
    expect(screen.queryByTestId("team-empty")).toBeNull();
  });

  it("shows the team empty line when every row ended", async () => {
    renderInspector(
      new FakeApiClient({
        liveRows: MIXED_ROWS.filter((row) =>
          ["RETURNED", "ACCEPTED", "REJECTED", "BLOCKED"].includes(row.status),
        ).map((row) => ({ ...row })),
      }),
    );
    expect(await screen.findByTestId("team-empty")).toBeTruthy();
    expect(screen.queryByTestId("team-rows")).toBeNull();
  });
});
