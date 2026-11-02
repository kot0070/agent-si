/** @vitest-environment jsdom */
// FXDESIGN8 (L-151 C1 conflict): Inspector Team-now lists every served row,
// including finished runs: after a run the rail still shows the last run's
// team with its real state (real state or none, never an Unknown chip).
// The old N1 drop-ended-rows pin is superseded; see TEST_CHANGES.
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

describe("fxdesign8 team-now finished rows", () => {
  it("keeps ended rows with their real state", async () => {
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
      expect(await screen.findByTestId(`team-row-${agent}`)).toBeTruthy();
    }
    expect(screen.queryByTestId("team-empty")).toBeNull();
  });

  it("shows the team empty line only when no rows are served", async () => {
    renderInspector(new FakeApiClient({ liveRows: [] }));
    expect(await screen.findByTestId("team-empty")).toBeTruthy();
    expect(screen.queryByTestId("team-rows")).toBeNull();
  });
});
