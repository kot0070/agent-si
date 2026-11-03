/** @vitest-environment jsdom */
// FXQACAT Q3 (RED->GREEN): Tests tab rail header (served bases, last plan
// name + served time, catalog link); 404 on a new project stays a plain
// empty state and logs nothing. Only global fetch is faked.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { TestsTab } from "../TestsTab";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubQ3(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (
        url === "/api/v1/teststage/plans/latest?project_id=p-t1" &&
        method === "GET"
      ) {
        return jsonBody({ project_id: "p-t1", plan_id: "plan-t1" });
      }
      if (
        url === "/api/v1/teststage/runs/latest?project_id=p-t1" &&
        method === "GET"
      ) {
        return jsonBody({
          project_id: "p-t1",
          plan_id: "plan-t1",
          run_id: "run-t1",
          started_at: "2026-11-02T10:00:00+00:00",
        });
      }
      if (
        url === "/api/v1/teststage/tests-view?plan_id=plan-t1&run_id=run-t1" &&
        method === "GET"
      ) {
        return jsonBody({
          plan_id: "plan-t1",
          run_id: "run-t1",
          active: 1,
          passed: 1,
          remaining: 0,
          rows: [
            {
              test_id: "t-boot",
              status: "PASS",
              output_ref: null,
              kind: "CODE",
            },
          ],
          settings_controls: [],
        });
      }
      if (
        url === "/api/v1/teststage/plans/latest?project_id=p-t2" &&
        method === "GET"
      ) {
        return jsonBody({ project_id: "p-t2", plan_id: "plan-t2" });
      }
      if (
        url === "/api/v1/teststage/runs/latest?project_id=p-t2" &&
        method === "GET"
      ) {
        return jsonBody({
          project_id: "p-t2",
          plan_id: "plan-t2",
          run_id: "run-t2",
        });
      }
      if (
        url === "/api/v1/teststage/tests-view?plan_id=plan-t2&run_id=run-t2" &&
        method === "GET"
      ) {
        return jsonBody({
          plan_id: "plan-t2",
          run_id: "run-t2",
          active: 0,
          passed: 0,
          remaining: 0,
          rows: [],
          settings_controls: [],
        });
      }
      if (url === "/api/v1/teststage/bases" && method === "GET") {
        return jsonBody({
          bases: [
            { base_id: "base-code-fast", kind: "CODE", origin: "builtin" },
          ],
        });
      }
      if (
        url === "/api/v1/teststage/plans/latest?project_id=p-new" &&
        method === "GET"
      ) {
        return jsonBody({ code: "CONTEXT_MISSING" }, 404);
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  stubQ3();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetLocaleForTests();
});

describe("fxqacat tests tab header", () => {
  it("shows served bases, last plan name plus served time, catalog link", async () => {
    render(<TestsTab projectId="p-t1" />);
    expect(
      (await screen.findByTestId("tests-bases")).textContent ?? "",
    ).toContain("base-code-fast");
    const last = (await screen.findByTestId("tests-last-plan")).textContent;
    expect(last ?? "").toContain("plan-t1");
    expect(last ?? "").toContain("2026-11-02");
    expect(
      screen.getByTestId("tests-catalog-link").getAttribute("href"),
    ).toBe("/settings/qacatalog");
  });

  it("shows the plan name with no time line when none is served", async () => {
    render(<TestsTab projectId="p-t2" />);
    const last = (await screen.findByTestId("tests-last-plan")).textContent;
    expect(last ?? "").toContain("plan-t2");
    expect(last ?? "").not.toContain("2026");
  });

  it("a new project reads a plain empty state and logs nothing", async () => {
    const errors: unknown[][] = [];
    const orig = console.error;
    console.error = (...args: unknown[]) => {
      errors.push(args);
    };
    try {
      render(<TestsTab projectId="p-new" />);
      expect(await screen.findByTestId("tests-empty")).toBeTruthy();
      expect(
        (await screen.findByTestId("tests-counters-active")).textContent,
      ).toBe("0");
    } finally {
      console.error = orig;
    }
    expect(errors).toEqual([]);
  });
});
