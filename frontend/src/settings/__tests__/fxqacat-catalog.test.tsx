/** @vitest-environment jsdom */
// FXQACAT Q1+Q2 (RED->GREEN): Settings Test-catalog section on the real
// page. Only global fetch is faked; the real QaCatalogSection renders.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { QaCatalogSection } from "../QaCatalogSection";

const SUMMARY = {
  catalog_ref: "catalog-v2",
  version: 2,
  version_sha_short: "abcdef12",
  bases: 4,
  tests_total: 3,
  kinds: { CODE: 1, AI: 1, HUMAN: 1 },
};

const TESTS = {
  catalog_ref: "catalog-v2",
  version: 2,
  total: 3,
  tests: [
    {
      id: "STA-001",
      group: "STA",
      intent: "static lint is clean",
      kind: "CODE-STATIC",
      priority: "P0",
      runner: "static_lint",
    },
    {
      id: "REQ-001",
      group: "REQ",
      intent: "requirements read",
      kind: "AI",
      priority: "P1",
      runner: null,
    },
    {
      id: "FUN-001",
      group: "FUN",
      intent: "operator sign-off",
      kind: "HUMAN",
      priority: "P2",
      runner: null,
    },
  ],
};

const HISTORY = {
  catalog_ref: "catalog-frozen-v1",
  active: { version: 1, sha_short: "a1b2c3d4", created_at: "2026-10-26T00:00:00Z" },
  versions: [{ version: 1, sha_short: "a1b2c3d4", active: true }],
  changelog: [
    {
      version: 1,
      change: "initial frozen catalog",
      changed_at: "2026-10-26T00:00:00Z",
      changed_by: "owner",
    },
  ],
};

const BASES = {
  bases: [
    { base_id: "base-code-fast", kind: "CODE", origin: "builtin" },
    { base_id: "base-ai-judge", kind: "AI", origin: "builtin" },
  ],
};

const CONTRACT = {
  contract_version: "1.0.0",
  policy: "built-in runners always run; a user runner runs only after approval",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubCatalog(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url === "/api/v1/teststage/catalog/summary" && method === "GET") {
        return jsonBody(SUMMARY);
      }
      if (url === "/api/v1/teststage/catalog/tests" && method === "GET") {
        return jsonBody(TESTS);
      }
      if (url === "/api/v1/teststage/catalog/history" && method === "GET") {
        return jsonBody(HISTORY);
      }
      if (url === "/api/v1/teststage/bases" && method === "GET") {
        return jsonBody(BASES);
      }
      if (url === "/api/v1/teststage/runner-contract" && method === "GET") {
        return jsonBody(CONTRACT);
      }
      if (url === "/api/v1/teststage/bases/attach" && method === "POST") {
        return jsonBody({
          base_id: "hdcheck-base",
          kind: "CODE",
          origin: "attached",
        });
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  stubCatalog();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetLocaleForTests();
});

describe("fxqacat catalog section", () => {
  it("renders active version, counters, versions, rows and changelog", async () => {
    render(<QaCatalogSection />);
    expect(await screen.findByTestId("qacatalog-section")).toBeTruthy();
    expect(
      (await screen.findByTestId("qacatalog-version")).textContent ?? "",
    ).toContain("abcdef12");
    const counters = (
      await screen.findByTestId("qacatalog-counters")
    ).textContent;
    for (const want of ["4", "3", "1"]) {
      expect(counters ?? "").toContain(want);
    }
    expect(
      await screen.findByTestId("qacatalog-row-STA-001"),
    ).toBeTruthy();
    expect(await screen.findByTestId("qacatalog-row-REQ-001")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("qacatalog-changelog-toggle"));
    expect(
      (await screen.findByTestId("qacatalog-changelog")).textContent ?? "",
    ).toContain("initial frozen catalog");
  });

  it("filters rows by kind and search", async () => {
    render(<QaCatalogSection />);
    await screen.findByTestId("qacatalog-row-STA-001");
    fireEvent.change(screen.getByTestId("qacatalog-filter-kind"), {
      target: { value: "AI" },
    });
    expect(screen.queryByTestId("qacatalog-row-STA-001")).toBeNull();
    expect(await screen.findByTestId("qacatalog-row-REQ-001")).toBeTruthy();
    fireEvent.change(screen.getByTestId("qacatalog-filter-kind"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByTestId("qacatalog-filter-search"), {
      target: { value: "sign-off" },
    });
    expect(screen.queryByTestId("qacatalog-row-STA-001")).toBeNull();
    expect(await screen.findByTestId("qacatalog-row-FUN-001")).toBeTruthy();
  });

  it("import stages a proposal and activate confirms it active", async () => {
    render(<QaCatalogSection />);
    await screen.findByTestId("qacatalog-row-STA-001");
    const file = new File(
      [JSON.stringify({ bases: [{ base_id: "hdcheck-base", kind: "CODE" }] })],
      "base.json",
      { type: "application/json" },
    );
    fireEvent.change(screen.getByTestId("qacatalog-import-file"), {
      target: { files: [file] },
    });
    expect(
      (await screen.findByTestId("qacatalog-proposal")).textContent ?? "",
    ).toContain("hdcheck-base");
    fireEvent.click(screen.getByTestId("qacatalog-activate"));
    expect(
      await screen.findByTestId("qacatalog-activate-confirm"),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByTestId("qacatalog-activate-confirm-yes"),
    );
    expect(
      (await screen.findByTestId("qacatalog-active-note")).textContent ?? "",
    ).toContain("hdcheck-base");
  });
});
