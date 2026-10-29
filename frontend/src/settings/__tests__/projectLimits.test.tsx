/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { ProjectLimitsSection } from "../projectLimits";

const PROJECT_ID = "p-1";
const STEP_LIMITS_URL = `/api/v1/projects/${PROJECT_ID}/step-limits`;
const BUDGET_URL = `/api/v1/budget?project_id=${PROJECT_ID}`;

// FAKE-OF: GET /api/v1/projects/{id}/step-limits (R349A served limits row).
let taskValue = 40;
// FAKE-OF: GET /api/v1/projects/{id}/step-limits (R349A served limits row).
let chatValue = 15;

interface SeenPut {
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

const seenPuts: SeenPut[] = [];

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  taskValue = 40;
  chatValue = 15;
  seenPuts.length = 0;
  setUiToken("test-ui-token");
  vi.stubGlobal(
    "fetch",
    async (
      url: unknown,
      init?: { method?: string; headers?: Record<string, string>; body?: string },
    ) => {
      const target = String(url);
      if (target === BUDGET_URL) {
        // FAKE-OF: GET /api/v1/budget (budget/routes get_budget real shape).
        return jsonResponse({
          project_id: PROJECT_ID,
          budget: {
            hard_limit: "5.00",
            spent: "0",
            reserved: "0",
            currency: "USD",
          },
        });
      }
      if (target === STEP_LIMITS_URL && (init?.method ?? "GET") === "PUT") {
        const body = JSON.parse(init?.body ?? "{}") as {
          task_max_steps: number;
          chat_max_steps: number;
        };
        taskValue = body.task_max_steps;
        chatValue = body.chat_max_steps;
        seenPuts.push({
          url: target,
          headers: { ...(init?.headers ?? {}) },
          body,
        });
        return jsonResponse({
          project_id: PROJECT_ID,
          task_max_steps: taskValue,
          chat_max_steps: chatValue,
          decision_ref: "steplimits:p-1:000001",
        });
      }
      if (target === STEP_LIMITS_URL) {
        return jsonResponse({
          project_id: PROJECT_ID,
          task_max_steps: taskValue,
          chat_max_steps: chatValue,
        });
      }
      return jsonResponse({ detail: "not found" }, 404);
    },
  );
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("ProjectLimitsSection", () => {
  it("renders the real section with both step values and the budget line", async () => {
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    expect(await screen.findByTestId("project-limits-section")).toBeTruthy();
    expect(
      await screen.findByText(t("settings.project.title")),
    ).toBeTruthy();
    expect(
      screen.getByText(t("settings.project.purpose")),
    ).toBeTruthy();
    const task = (await screen.findByTestId(
      "project-limits-task",
    )) as HTMLInputElement;
    const chat = screen.getByTestId(
      "project-limits-chat",
    ) as HTMLInputElement;
    expect(task.value).toBe("40");
    expect(chat.value).toBe("15");
    const budget = await screen.findByTestId("project-limits-budget");
    expect(budget.textContent).toContain("5.00");
    expect(budget.textContent).toContain("USD");
  });

  it("saves a changed value with the token header and shows the new value after reload", async () => {
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    const task = (await screen.findByTestId(
      "project-limits-task",
    )) as HTMLInputElement;
    fireEvent.change(task, { target: { value: "100" } });
    fireEvent.click(await screen.findByTestId("project-limits-save"));
    const reloaded = (await screen.findByDisplayValue(
      "100",
    )) as HTMLInputElement;
    expect(reloaded.value).toBe("100");
    expect(seenPuts).toHaveLength(1);
    const put = seenPuts[0];
    expect(put).toBeDefined();
    expect(put?.url).toBe(STEP_LIMITS_URL);
    expect(put?.headers["x-ui-session-token"]).toBe("test-ui-token");
    expect((put?.headers["x-actor"] ?? "").length).toBeGreaterThan(0);
    expect(put?.body).toEqual({ task_max_steps: 100, chat_max_steps: 15 });
  });

  it("shows an honest error when the server refuses the save", async () => {
    vi.stubGlobal(
      "fetch",
      async (url: unknown, init?: { method?: string; body?: string }) => {
        const target = String(url);
        if (target === BUDGET_URL) {
          return jsonResponse({
            project_id: PROJECT_ID,
            budget: {
              hard_limit: "5.00",
              spent: "0",
              reserved: "0",
              currency: "USD",
            },
          });
        }
        if (target === STEP_LIMITS_URL && (init?.method ?? "GET") === "PUT") {
          return jsonResponse({ detail: "BUDGET_CAPPED: refused" }, 400);
        }
        return jsonResponse({
          project_id: PROJECT_ID,
          task_max_steps: 40,
          chat_max_steps: 15,
        });
      },
    );
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    await screen.findByTestId("project-limits-task");
    fireEvent.click(screen.getByTestId("project-limits-save"));
    expect(await screen.findByTestId("project-limits-error")).toBeTruthy();
  });
});
