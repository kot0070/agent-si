/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectLimitsSection } from "../projectLimits";

const PROJECT_ID = "p-1";
const STEP_LIMITS_URL = `/api/v1/projects/${PROJECT_ID}/step-limits`;
const BUDGET_URL = `/api/v1/budget?project_id=${PROJECT_ID}`;
const LIMITS_URL = "/api/v1/budget/limits";

let caps: Record<string, string> = { acme: "5.00" };

interface SeenPost {
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

const seenPosts: SeenPost[] = [];

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function budgetPayload() {
  return {
    project_id: PROJECT_ID,
    budget: {
      hard_limit: "100.00",
      spent: "2.00",
      reserved: "0",
      currency: "USD",
      provider_spend_caps: { ...caps },
      provider_spending: {
        acme: { spent: "2.00", reserved: "0", cap: caps["acme"] ?? null },
      },
    },
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  caps = { acme: "5.00" };
  seenPosts.length = 0;
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
        return jsonResponse(budgetPayload());
      }
      if (target === LIMITS_URL && (init?.method ?? "GET") === "POST") {
        const body = JSON.parse(init?.body ?? "{}") as {
          project_id: string;
          provider_spend_caps: Record<string, string>;
        };
        caps = { ...body.provider_spend_caps };
        seenPosts.push({
          url: target,
          headers: { ...(init?.headers ?? {}) },
          body,
        });
        return jsonResponse({
          project_id: PROJECT_ID,
          budget: budgetPayload().budget,
          provider_spend_caps: { ...caps },
        });
      }
      if (target === STEP_LIMITS_URL) {
        return jsonResponse({
          project_id: PROJECT_ID,
          task_max_steps: 40,
          chat_max_steps: 15,
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

describe("ProjectLimitsSection provider caps", () => {
  it("shows per-provider spent vs cap from the real budget shape", async () => {
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    const spending = await screen.findByTestId("project-limits-spending");
    expect(spending.textContent).toContain("acme: 2.00 / 5.00 USD");
    const field = (await screen.findByTestId(
      "project-limits-caps",
    )) as HTMLInputElement;
    expect(field.value).toBe("acme:5.00");
  });

  it("saves edited caps through POST /api/v1/budget/limits", async () => {
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    const field = (await screen.findByTestId(
      "project-limits-caps",
    )) as HTMLInputElement;
    fireEvent.change(field, { target: { value: "acme:7.00" } });
    fireEvent.click(await screen.findByTestId("project-limits-caps-save"));
    await screen.findByDisplayValue("acme:7.00");
    expect(seenPosts).toHaveLength(1);
    expect(seenPosts[0]?.url).toBe(LIMITS_URL);
    expect(seenPosts[0]?.headers["x-ui-session-token"]).toBe("test-ui-token");
    expect(seenPosts[0]?.body).toEqual({
      project_id: PROJECT_ID,
      provider_spend_caps: { acme: "7.00" },
    });
  });
});
