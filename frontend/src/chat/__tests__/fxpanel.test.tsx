/** @vitest-environment jsdom */
// FXPANEL P10 through the REAL page: the Tokens toggle is a visible
// labelled 32px target in en + uk; clicking expands to kit-expanded-bar.
// The hit-box rule is locked by a stylesheet assertion (zero-size guard).
// Locale driver: ui.card.toggle + shell.cards.tokens.* in en + uk.
// Network boundary only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from "node:fs";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";

const APP_PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

function jsonApp(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubApp(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/projects") {
      return jsonApp({ projects: [APP_PROJECT] });
    }
    if (url === "/api/v1/agents/live") {
      return jsonApp({
        agents: [
          {
            agent: "agent-1",
            scope: "scope-1",
            deliverable: "part-1",
            status: "RUNNING",
            role: "manager",
            model: "m-1",
            tokens: { input: 400, output: 600 },
          },
        ],
      });
    }
    return jsonApp({ code: "FXPANEL_UNEXPECTED_API" }, 404);
  });
}

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  stubApp();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxpanel P10 tokens toggle", () => {
  it("toggle carries its label and expands to the bar in English", async () => {
    setLocale("en");
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    // FXFACTS F10: the tokens card lives in More.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    const toggle = await screen.findByTestId("kit-toggle-fx-tokens");
    expect(toggle.getAttribute("aria-label")).toBe(t("ui.card.toggle"));
    expect(toggle.classList.contains("fx-kit-toggle")).toBe(true);
    expect(
      screen
        .getByTestId("kit-metric-fx-tokens")
        .querySelector('[data-testid="kit-expanded-bar"]'),
    ).toBeNull();
    fireEvent.click(toggle);
    expect(
      screen
        .getByTestId("kit-metric-fx-tokens")
        .querySelector('[data-testid="kit-expanded-bar"]'),
    ).toBeTruthy();
  });

  it("toggle carries its label and expands to the bar in Ukrainian", async () => {
    setLocale("uk");
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    // FXFACTS F10: the tokens card lives in More.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    const toggle = await screen.findByTestId("kit-toggle-fx-tokens");
    expect(toggle.getAttribute("aria-label")).toBe("Показати деталі");
    fireEvent.click(toggle);
    expect(
      screen
        .getByTestId("kit-metric-fx-tokens")
        .querySelector('[data-testid="kit-expanded-bar"]'),
    ).toBeTruthy();
  });

  it("the kit toggle keeps an explicit hit box (never zero-size)", () => {
    const shellCss = readFileSync("src/ui/shell.css", "utf8") as string;
    const block =
      /\.fx-kit-toggle\s*\{([^}]*)\}/.exec(shellCss)?.[1] ?? "";
    expect(block).toMatch(/width:\s*32px/);
    expect(block).toMatch(/height:\s*32px/);
    expect(block).not.toMatch(/min-width:\s*28px/);
  });
});
