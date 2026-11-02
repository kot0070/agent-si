/** @vitest-environment jsdom */
// K07HTTP2 1646/1647 (UI_DELTA-14/15 role profile map) + 1648 (BP06-6 one
// row per role per project) over the REAL server path (only global fetch
// stubbed, never FakeApiClient). The stub answers the role route with the
// backend shape from src/agent_si/backend/pools_routes.py:96
// (_profile_payload) plus :343 (get_role read) and :359 (set_role write).
// Asserts the request URL plus method plus write-token header and the
// rendered editor text.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { readRoleProfile, readRoleProfiles, saveRoleProfile } from "../index";
import { RoleProfileEditor } from "../index";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";

const TOKEN = "tok-k07-h2-settings";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const serverRows = new Map<string, Record<string, unknown>>();

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
}

const seen: SeenRequest[] = [];

function rowKey(projectId: string, role: string): string {
  return `${projectId}::${role}`;
}

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubBoundary(): void {
  serverRows.clear();
  seen.length = 0;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    seen.push({
      url,
      method,
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
    });
    let body: unknown = null;
    if (typeof init?.body === "string" && init.body.length > 0) {
      try {
        body = JSON.parse(init.body) as unknown;
      } catch {
        body = null;
      }
    }
    if (url === "/api/v1/routing/role" && method === "PUT") {
      const record = (body ?? {}) as Record<string, unknown>;
      const row: Record<string, unknown> = {
        role: String(record["role"] ?? ""),
        project_id: String(record["project_id"] ?? ""),
        mode: String(record["mode"] ?? ""),
        provider: record["provider"] ?? null,
        model: record["model"] ?? null,
        binding: "DEFAULT",
        version: 1,
      };
      serverRows.set(`${row["project_id"]}::${row["role"]}`, row);
      return jsonBody({ ok: true, profile: row });
    }
    if (url.startsWith("/api/v1/routing/role?") && method === "GET") {
      const query = new URLSearchParams(url.split("?")[1] ?? "");
      const row = serverRows.get(
        rowKey(query.get("project_id") ?? "", query.get("role") ?? ""),
      );
      if (row === undefined) {
        return jsonBody({ error: "missing" }, 404);
      }
      return jsonBody({ profile: row });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = TOKEN;
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function expectPutGuarded(): void {
  const puts = seen.filter(
    (request) => request.url === "/api/v1/routing/role" && request.method === "PUT",
  );
  expect(puts.length).toBeGreaterThanOrEqual(1);
  for (const put of puts) {
    expect(put.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(put.headers["x-actor"]).toBe("ui");
  }
  for (const request of seen) {
    expect(request.url).not.toContain("token=");
  }
}

describe("k07http2 settings role profiles over the server path", () => {
  it("1648: one row per role per project persists across restart", async () => {
    expect(
      (await saveRoleProfile("project-1", { role: "manager", mode: "AUTO" })).ok,
    ).toBe(true);
    expect(
      (
        await saveRoleProfile("project-1", {
          role: "worker",
          mode: "PINNED",
          provider: "acme",
          model: "m1",
        })
      ).ok,
    ).toBe(true);
    expect(
      (
        await saveRoleProfile("project-2", {
          role: "manager",
          mode: "PINNED",
          provider: "acme",
          model: "m1",
        })
      ).ok,
    ).toBe(true);
    expect(await readRoleProfile("project-1", "manager")).toEqual({ mode: "AUTO" });
    expect(await readRoleProfile("project-1", "worker")).toEqual({
      mode: "PINNED",
      provider: "acme",
      model: "m1",
    });
    expect(await readRoleProfile("project-2", "manager")).toEqual({
      mode: "PINNED",
      provider: "acme",
      model: "m1",
    });
    // Restart: fresh reads (server rows survive) keep every row in place.
    expect(await readRoleProfile("project-1", "manager")).toEqual({ mode: "AUTO" });
    expect(await readRoleProfile("project-2", "worker")).toBeUndefined();
    expectPutGuarded();
    const gets = seen.filter(
      (request) => request.url.startsWith("/api/v1/routing/role?") && request.method === "GET",
    );
    expect(gets.length).toBeGreaterThanOrEqual(1);
    for (const get of gets) {
      expect(get.headers["x-ui-session-token"]).toBeUndefined();
    }
  });

  it("1646/1647: the editor renders the real screen and reloads the saved map", async () => {
    const shown = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RoleProfileEditor projectId="project-7" role="manager" />
      </ApiClientProvider>,
    );
    expect(screen.getByText(en.settings.roleProfile.title)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modeLabel), {
      target: { value: "PINNED" },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.providerLabel), {
      target: { value: "acme" },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modelLabel), {
      target: { value: "m1" },
    });
    await waitFor(() => {
      expect(serverRows.get(rowKey("project-7", "manager"))?.["mode"]).toBe("PINNED");
    });
    expect(await readRoleProfile("project-7", "manager")).toEqual({
      mode: "PINNED",
      provider: "acme",
      model: "m1",
    });
    expect(await readRoleProfiles("project-7")).toEqual({
      manager: { mode: "PINNED", provider: "acme", model: "m1" },
    });
    shown.unmount();
    cleanup();
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RoleProfileEditor projectId="project-7" role="manager" />
      </ApiClientProvider>,
    );
    await waitFor(() => {
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
      ).toBe("PINNED");
    });
    expect(
      (screen.getByLabelText(en.settings.roleProfile.providerLabel) as HTMLInputElement).value,
    ).toBe("acme");
    expectPutGuarded();
  });

  it("1646: offline cache reads back after the server value, never instead", async () => {
    expect(
      (await saveRoleProfile("project-1", { role: "manager", mode: "AUTO" })).ok,
    ).toBe(true);
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("offline");
    });
    expect(await readRoleProfiles("project-1")).toEqual({ manager: { mode: "AUTO" } });
  });
});
