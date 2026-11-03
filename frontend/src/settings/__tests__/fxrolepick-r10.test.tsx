// FXROLEPICK R10: one routine-offload switch in the project team
// limits (served GET/PUT, fake at the network only). The change is
// journaled server-side; a refusal shows plain words.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectLimitsSection } from "../projectLimits";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const seen: string[] = [];

function stubNetwork(putStatus: number, putBody: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      seen.push(`${method} ${url}`);
      if (url === "/api/v1/projects/p-10/step-limits") {
        return jsonBody({ project_id: "p-10", task_max_steps: 8, chat_max_steps: 4 });
      }
      if (url === "/api/v1/budget?project_id=p-10") {
        return jsonBody({
          project_id: "p-10",
          budget: { hard_limit: "100", spent: "10", reserved: "5", currency: "USD" },
        });
      }
      if (url === "/api/v1/projects/p-10/parallel-parts") {
        return method === "GET"
          ? jsonBody({ project_id: "p-10", max_parallel_parts: 1 })
          : jsonBody({ project_id: "p-10", max_parallel_parts: 1 });
      }
      if (url === "/api/v1/projects/p-10/team") {
        return method === "GET"
          ? jsonBody({ project_id: "p-10", team: "on" })
          : jsonBody({ project_id: "p-10", team: "on" });
      }
      if (url === "/api/v1/projects/p-10/offload?role=worker") {
        return jsonBody({ project_id: "p-10", role: "worker", enabled: false });
      }
      if (url === "/api/v1/projects/p-10/offload" && method === "PUT") {
        return jsonBody(putBody, putStatus);
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

describe("R10 routine offload switch", () => {
  it("reads the served switch and saves on with one plain hint", async () => {
    stubNetwork(200, { project_id: "p-10", role: "worker", enabled: true, decision_ref: "d-1" });
    render(<ProjectLimitsSection projectId="p-10" />);
    const box = (await screen.findByTestId("project-limits-offload")) as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(screen.getByTestId("project-limits-offload-hint").textContent).not.toBe("");
    fireEvent.click(box);
    fireEvent.click(await screen.findByTestId("project-limits-offload-save"));
    await screen.findByText("Saved.");
    expect(seen).toContain("PUT /api/v1/projects/p-10/offload");
  });

  it("a refusal shows plain words, never a bare code", async () => {
    stubNetwork(400, { detail: "POLICY_CONFLICT: auditor role never offloads" });
    render(<ProjectLimitsSection projectId="p-10" />);
    const box = (await screen.findByTestId("project-limits-offload")) as HTMLInputElement;
    fireEvent.click(box);
    fireEvent.click(await screen.findByTestId("project-limits-offload-save"));
    const error = await screen.findByTestId("project-limits-offload-error");
    expect(error.textContent).toContain("auditor role never offloads");
    expect(error.textContent).not.toContain("POLICY_CONFLICT");
  });
});
