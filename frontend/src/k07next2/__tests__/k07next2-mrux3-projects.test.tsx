/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-3: the REAL ProjectsOverview over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served projects schema from
// src/agent_si/backend/read_routes.py:168).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { ProjectsOverview } from "../ProjectsOverview";
import type { ProjectsDoc } from "../k07next2Api";

const SERVED_PROJECTS: ProjectsDoc = { projects: [] };

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
    if (String(input) === "/api/v1/projects") {
      return jsonBody(SERVED_PROJECTS);
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

describe("k07next2 M-R-UX-3 projects over the real screen", () => {
  it("renders the served empty project list", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectsOverview />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-projects");
    expect(seen).toContain("/api/v1/projects");
    expect(screen.getByText(en.projects.list.title)).toBeTruthy();
    expect(screen.getByText(en.projects.list.empty)).toBeTruthy();
  });
});
