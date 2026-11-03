/** @vitest-environment jsdom */
// FXFACTS F11 RED: the local benchmark "find models" flow works from the
// page. Choose-folder fills the path (same pick-folder route as Projects);
// the scan button enables once a folder is set with a visible reason
// while empty; pre-scan the list names the choose step; an empty scan
// names the folder plus what it looked for; errors read plainly. The API
// is mocked at the network (no real Ollama or LM Studio).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { LocalBenchTab } from "../LocalBenchTab";
import { HttpLocalBenchClient } from "../LocalBenchClient";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubApi(
  pick: Response,
  scan: (url: string) => Response,
): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown): Promise<Response> => {
      const url = String(input);
      if (url === "/api/v1/sidecar/pick-folder") {
        return pick;
      }
      if (url.startsWith("/api/v1/local/bench/scan")) {
        return scan(url);
      }
      return jsonBody({ code: "FXFACTS11_UNEXPECTED_API" }, 404);
    },
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

function renderTab(): void {
  render(<LocalBenchTab client={new HttpLocalBenchClient()} />);
}

describe("fxfacts11 local bench find-models flow", () => {
  it("asks for a folder before any scan, with a reason on the scan button", async () => {
    stubApi(jsonBody({ code: "NONE" }, 409), () => jsonBody([]));
    renderTab();
    expect(await screen.findByTestId("localbench-tab")).toBeTruthy();
    expect(screen.getByTestId("localbench-choose-hint").textContent).toContain(
      "folder",
    );
    const scan = screen.getByTestId("localbench-scan") as HTMLButtonElement;
    expect(scan.disabled).toBe(true);
    expect(
      screen.getByTestId("localbench-scan-hint").textContent?.length,
    ).toBeGreaterThan(0);
  });

  it("choose folder fills the path, empty scan names the folder", async () => {
    stubApi(jsonBody({ path: "C:/models" }), () => jsonBody([]));
    renderTab();
    expect(await screen.findByTestId("localbench-tab")).toBeTruthy();
    fireEvent.click(screen.getByTestId("localbench-choose"));
    const path = (await screen.findByTestId(
      "localbench-path",
    )) as HTMLInputElement;
    await screen.findByDisplayValue("C:/models");
    expect(path.value).toBe("C:/models");
    const scan = screen.getByTestId("localbench-scan") as HTMLButtonElement;
    expect(scan.disabled).toBe(false);
    fireEvent.click(scan);
    const empty = await screen.findByTestId("localbench-models-empty");
    expect(empty.textContent).toContain("C:/models");
  });

  it("scan errors read as a plain sentence with the reason", async () => {
    stubApi(jsonBody({ path: "C:/models" }), () =>
      jsonBody({ code: "SCAN_REFUSED", detail: "outside the allowlist" }, 400),
    );
    renderTab();
    expect(await screen.findByTestId("localbench-tab")).toBeTruthy();
    fireEvent.click(screen.getByTestId("localbench-choose"));
    await screen.findByDisplayValue("C:/models");
    fireEvent.click(screen.getByTestId("localbench-scan"));
    const error = await screen.findByTestId("localbench-scan-error");
    expect(error.textContent).toContain("outside the allowlist");
  });

  it("pre-fills the last used path from the stored scan", async () => {
    window.localStorage.setItem(
      "agentsi.localbench.scan",
      JSON.stringify({ path: "C:/old-models", models: [] }),
    );
    stubApi(jsonBody({ code: "NONE" }, 409), () => jsonBody([]));
    renderTab();
    const path = (await screen.findByTestId(
      "localbench-path",
    )) as HTMLInputElement;
    expect(path.value).toBe("C:/old-models");
  });
});
