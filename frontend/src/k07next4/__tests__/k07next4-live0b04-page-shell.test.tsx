/** @vitest-environment jsdom */
// K07NEXT4 LIVE0B-04: the REAL ConsolePageShell over a fresh HttpApiClient
// (only global fetch replaced, quoting the served page shell schema
// from src/agent_si/http/k07next4.py page_shell).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { ConsolePageShell } from "../ConsolePageShell";

const SERVED_SHELL = {
  row: "LIVE0B-04",
  title_key: "shell.sidebar.projects",
  title: "Projects",
  console_class: "agent-si-console",
};

const seen: string[] = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  vi.stubGlobal("fetch", async (input: unknown) => {
    seen.push(String(input));
    if (String(input) === "/api/v1/app/page-shell") {
      return jsonBody(SERVED_SHELL);
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next4 LIVE0B-04 page shell over the real screen", () => {
  it("renders the title inside the console styling hook", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ConsolePageShell />
      </ApiClientProvider>,
    );
    const shell = await screen.findByTestId("k07next4-page-shell");
    expect(seen).toContain("/api/v1/app/page-shell");
    expect(shell.className).toContain("agent-si-console");
    expect(en.shell.sidebar.projects).toBe("Projects");
    expect(screen.getAllByText("Projects")).toHaveLength(2);
  });
});
