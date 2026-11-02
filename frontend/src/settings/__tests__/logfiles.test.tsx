/**
 * @vitest-environment jsdom
 *
 * FXLOG Diagnostics line: Settings > Diagnostics shows the sidecar log
 * folder path, and the button POSTs /api/v1/sidecar/open-logs. The path
 * stays when reveal fails.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DiagnosticsSection } from "../DiagnosticsSection";

const LOGS_DIR = "D:\\agent\\data\\logs";

function stubFetch(openStatus: number): string[] {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    async (input: unknown) => {
      const url = String(input);
      calls.push(url);
      if (url === "/api/v1/sidecar/about") {
        return { ok: true, status: 200, json: async () => ({ logs_dir: LOGS_DIR }) };
      }
      if (url === "/api/v1/sidecar/open-logs") {
        return { ok: openStatus < 400, status: openStatus, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    },
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Diagnostics log folder line", () => {
  it("shows the log path and opens it through the sidecar", async () => {
    const calls = stubFetch(200);
    render(
      <MemoryRouter>
        <DiagnosticsSection />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("diagnostics-log-files")).toBeTruthy();
    expect(screen.getByTestId("diagnostics-log-files").textContent).toContain(LOGS_DIR);
    fireEvent.click(screen.getByTestId("diagnostics-open-logs"));
    await waitFor(() => expect(calls).toContain("/api/v1/sidecar/open-logs"));
  });

  it("keeps the path when reveal is unavailable", async () => {
    const calls = stubFetch(409);
    render(
      <MemoryRouter>
        <DiagnosticsSection />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("diagnostics-log-files")).toBeTruthy();
    fireEvent.click(screen.getByTestId("diagnostics-open-logs"));
    await waitFor(() => expect(calls).toContain("/api/v1/sidecar/open-logs"));
    expect(screen.getByTestId("diagnostics-log-files").textContent).toContain(LOGS_DIR);
  });
});
