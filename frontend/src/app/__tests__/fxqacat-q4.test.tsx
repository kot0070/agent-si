/** @vitest-environment jsdom */
// FXQACAT Q4 (RED->GREEN, Advisor ORDER 52): Tests tab plain explanation
// plus How-it-works carry the same three short lines (plan 870-871).
// Only global fetch is faked; the real TestsTab and HowItWorks render.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { TestsTab } from "../../projects/TestsTab";
import { HowItWorks } from "../HowItWorks";

const EN_LINES = [
  "Runs = agent work",
  "code tests = the project's own test suite",
  "local tests = catalog tests the app runs locally",
];

const UK_LINES = [
  "Запуски = робота агентів",
  "тести коду = власний набір тестів проєкту",
  "локальні тести = тести з каталогу, які програма виконує локально",
];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubQ4(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (
        url === "/api/v1/teststage/plans/latest?project_id=p-q4" &&
        method === "GET"
      ) {
        return jsonBody({ project_id: "p-q4", plan_id: "plan-q4" });
      }
      if (
        url === "/api/v1/teststage/runs/latest?project_id=p-q4" &&
        method === "GET"
      ) {
        return jsonBody({
          project_id: "p-q4",
          plan_id: "plan-q4",
          run_id: "run-q4",
        });
      }
      if (
        url === "/api/v1/teststage/tests-view?plan_id=plan-q4&run_id=run-q4" &&
        method === "GET"
      ) {
        return jsonBody({
          plan_id: "plan-q4",
          run_id: "run-q4",
          active: 0,
          passed: 0,
          remaining: 0,
          rows: [],
          settings_controls: [],
        });
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  stubQ4();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetLocaleForTests();
});

describe("fxqacat Q4 plain-words lines", () => {
  it("tests tab explainer carries the three short lines (en)", async () => {
    setLocale("en");
    render(<TestsTab projectId="p-q4" />);
    const explainer = await screen.findByTestId("tests-explainer");
    for (const line of EN_LINES) {
      expect(explainer.textContent ?? "").toContain(line);
    }
  });

  it("how-it-works carries the same three short lines (en)", async () => {
    setLocale("en");
    render(<HowItWorks />);
    const concepts = await screen.findByTestId("how-it-works-concepts");
    for (const line of EN_LINES) {
      expect(concepts.textContent ?? "").toContain(line);
    }
  });

  it("both surfaces carry the three lines in ukrainian (uk)", async () => {
    setLocale("uk");
    render(<TestsTab projectId="p-q4" />);
    const explainer = await screen.findByTestId("tests-explainer");
    for (const line of UK_LINES) {
      expect(explainer.textContent ?? "").toContain(line);
    }
    cleanup();
    render(<HowItWorks />);
    const concepts = await screen.findByTestId("how-it-works-concepts");
    for (const line of UK_LINES) {
      expect(concepts.textContent ?? "").toContain(line);
    }
  });
});
