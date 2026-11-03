// FXROLEPICK R11: attached bases list (GET /api/v1/kb/list), Detach
// posts to POST /api/v1/kb/detach and reads a plain result. Network
// is the only fake (global fetch).
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { DetachControl } from "../DetachControl";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const seen: string[] = [];

function stubNetwork(detachStatus: number, detachBody: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      seen.push(`${method} ${url}`);
      if (url === "/api/v1/kb/list?project_id=p-11") {
        return jsonBody([
          { kb_id: "kb-a", kind: "DEV_ROLE", project_id: "p-11", role: null },
          { kb_id: "kb-b", kind: "DEV_SHARED", project_id: "p-11", role: "worker" },
        ]);
      }
      if (url === "/api/v1/kb/detach" && method === "POST") {
        return jsonBody(detachBody, detachStatus);
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    }),
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R11 knowledge base detach", () => {
  it("lists attached bases and detaches with a plain result", async () => {
    stubNetwork(200, null);
    render(<DetachControl projectId="p-11" />);
    expect(await screen.findByTestId("kb-detach-row-kb-a")).toBeTruthy();
    expect(await screen.findByTestId("kb-detach-row-kb-b")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("kb-detach-kb-a"));
    expect(await screen.findByText("Detached kb-a.")).toBeTruthy();
    expect(screen.queryByTestId("kb-detach-row-kb-a")).toBeNull();
    expect(seen).toContain("POST /api/v1/kb/detach");
  });

  it("a refusal shows plain words", async () => {
    stubNetwork(400, { detail: { code: "KB_MISSING", message: "unknown base kb-a" } });
    render(<DetachControl projectId="p-11" />);
    fireEvent.click(await screen.findByTestId("kb-detach-kb-b"));
    const result = await screen.findByTestId("kb-detach-result");
    expect(result.textContent).toContain("unknown base kb-a");
    expect(result.textContent).not.toContain("KB_MISSING");
  });
});
