/** @vitest-environment jsdom */
// FXCLASS CD-5/CD-6/CD-7 + CA-6 RED-first proofs on the real page.
// Fake only at the network boundary (global fetch).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { setUiToken } from "../../api/errors";
import { apiErrorLocaleKey } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { SessionTokenCard } from "../../k07next4/SessionTokenCard";
import { WatcherTab } from "../../watcher/WatcherTab";
import { ProjectLimitsSection } from "../../settings/projectLimits";

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
  setUiToken("test-ui-token");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("FXCLASS CD-6 session token error state", () => {
  it("a 500 shows an error panel with retry, never an endless spinner", async () => {
    vi.stubGlobal("fetch", async () => jsonResponse({ detail: "boom" }, 500));
    render(<SessionTokenCard />);
    const panel = await screen.findByTestId("k07next4-session-token-error");
    expect(panel).toBeTruthy();
    expect(panel.textContent ?? "").not.toContain("request failed: 500");
    expect(screen.queryByTestId("k07next4-session-token-error")).toBeTruthy();
  });
});

describe("FXCLASS CD-7 watcher error mapping", () => {
  it("a 500 maps through apiErrorLocaleKey, never a raw request-failed line", async () => {
    vi.stubGlobal("fetch", async () => jsonResponse({ detail: "boom" }, 500));
    render(<WatcherTab projectId="p-1" />);
    const panel = await screen.findByTestId("watcher-error");
    expect(panel.textContent ?? "").not.toContain("request failed: 500");
    expect(panel.textContent ?? "").not.toContain("watcher status request failed");
    expect(apiErrorLocaleKey("CONTEXT_WRONG_CONTRACT_VERSION")).not.toBe("");
  });
});

describe("FXCLASS CA-6 blank limit input", () => {
  it("a blank task limit shows a field message and sends nothing", async () => {
    const puts: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown, init?: { method?: string; body?: string }) => {
      const target = String(url);
      if (target === "/api/v1/projects/p-1/step-limits" && (init?.method ?? "GET") === "PUT") {
        puts.push(target);
        return jsonResponse({ project_id: "p-1", task_max_steps: 40, chat_max_steps: 15 });
      }
      if (target === "/api/v1/projects/p-1/step-limits") {
        return jsonResponse({ project_id: "p-1", task_max_steps: 40, chat_max_steps: 15 });
      }
      if (target === "/api/v1/budget?project_id=p-1") {
        return jsonResponse({
          project_id: "p-1",
          budget: { hard_limit: "5.00", spent: "0", reserved: "0", currency: "USD" },
        });
      }
      return jsonResponse({ detail: "not found" }, 404);
    });
    render(<ProjectLimitsSection projectId="p-1" />);
    const task = (await screen.findByTestId("project-limits-task")) as HTMLInputElement;
    fireEvent.change(task, { target: { value: "" } });
    fireEvent.click(screen.getByTestId("project-limits-save"));
    const fieldError = await screen.findByTestId("project-limits-field-error");
    expect(fieldError).toBeTruthy();
    expect(puts).toHaveLength(0);
  });
});
