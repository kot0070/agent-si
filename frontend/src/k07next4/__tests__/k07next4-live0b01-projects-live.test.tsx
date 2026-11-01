/** @vitest-environment jsdom */
// K07NEXT4 LIVE0B-01: the REAL ProjectsLiveList over a fresh HttpApiClient
// (only global fetch replaced, quoting the served projects schemas
// from src/agent_si/http/k07next4.py projects_list/projects_create).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { ProjectsLiveList } from "../ProjectsLiveList";

const TOKEN = "tok-k07next4-live0b01";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const SERVED_PROJECTS = {
  row: "LIVE0B-01",
  projects: [{ project_id: "p-1", name: "seed-one", folder_ref: "f-1" }],
};

const seen: string[] = [];
let listed = false;

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
  listed = false;
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = TOKEN;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    seen.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (String(input) === "/api/v1/k07next4/projects") {
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        return jsonBody({
          row: "LIVE0B-01",
          project: {
            project_id: "p-2",
            name: "k07next4-new",
            folder_ref: "f-k07next4",
          },
        });
      }
      if (!listed) {
        listed = true;
        return jsonBody(SERVED_PROJECTS);
      }
      return jsonBody({
        row: "LIVE0B-01",
        projects: [
          ...SERVED_PROJECTS.projects,
          {
            project_id: "p-2",
            name: "k07next4-new",
            folder_ref: "f-k07next4",
          },
        ],
      });
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next4 LIVE0B-01 projects list over the real screen", () => {
  it("shows the new project after Add without a reload", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectsLiveList />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next4-projects-live");
    expect(seen).toContain("GET /api/v1/k07next4/projects");
    expect(screen.getByText(en.projects.list.title)).toBeTruthy();
    fireEvent.click(screen.getByText(en.tasks.creator.create));
    await screen.findByText("k07next4-new");
    expect(seen).toContain("POST /api/v1/k07next4/projects");
    expect(screen.getByText("seed-one")).toBeTruthy();
  });
});
