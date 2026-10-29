/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { ENDPOINTS, expandEndpoint } from "../../api/endpoints";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { TaskView } from "../TaskView";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function stubTurnsFetch(body: unknown): void {
  vi.stubGlobal(
    "fetch",
    async (url: unknown) => {
      expect(String(url)).toContain("/turns");
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  );
}

describe("task view turns", () => {
  it("renders both stored triples in order plus the counter", async () => {
    stubTurnsFetch({
      turns: [
        { plan: "plan-a", action: "action-a", observation: "obs-a" },
        { plan: "plan-b", action: "action-b", observation: "obs-b" },
      ],
      used: 2,
      limit: 40,
    });
    render(<TaskView taskId="t-1" />);
    const plans = await screen.findAllByTestId("task-turn-plan");
    expect(plans.map((node) => node.textContent)).toEqual([
      "plan-a",
      "plan-b",
    ]);
    expect(
      screen
        .getAllByTestId("task-turn-action")
        .map((node) => node.textContent),
    ).toEqual(["action-a", "action-b"]);
    expect(
      screen
        .getAllByTestId("task-turn-observation")
        .map((node) => node.textContent),
    ).toEqual(["obs-a", "obs-b"]);
    expect(screen.getByTestId("task-turns-counter").textContent).toContain(
      "2 / 40",
    );
    expect(
      screen.getByTestId("task-turns-counter").textContent,
    ).not.toContain("NaN");
  });

  it("renders the empty state plus a zero counter", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      async (url: unknown) => {
        seen.push(String(url));
        return new Response(
          JSON.stringify({ turns: [], used: 0, limit: 40 }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        );
      },
    );
    render(<TaskView taskId="t-9" />);
    expect(await screen.findByTestId("kit-empty-state")).toBeTruthy();
    expect(screen.getByTestId("task-turns-counter").textContent).toContain(
      "0 / 40",
    );
    expect(seen).toHaveLength(1);
    expect(seen[0]).toBe(`${expandEndpoint(ENDPOINTS.taskById, "t-9")}/turns`);
  });
});
