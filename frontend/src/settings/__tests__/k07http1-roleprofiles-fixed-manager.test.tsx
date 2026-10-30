/** @vitest-environment jsdom */
// K07HTTP1 UI_DELTA-15: manager PINNED PUT persists the fixed-manager
// fields and GET shows them, through the REAL RoleProfileEditor over a
// fresh HttpApiClient (only global fetch stubbed; no FakeApiClient).
// The stub mirrors the backend set_role manager branch
// (src/agent_si/backend/pools_routes.py:403 answers manager_profile with
// the fixed-manager fields) and the :96 _profile_payload shape; GET
// follows :343 get_role (404 when no row).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { RoleProfileEditor } from "../index";
import en from "../../locale/en.json";

const TOKEN = "tok-k07-fixed-manager";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const FROZEN_ROLES = ["director", "manager", "worker", "auditor", "watcher"];

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

const serverRows = new Map<string, Record<string, unknown>>();
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
    let body: unknown = null;
    if (typeof init?.body === "string" && init.body.length > 0) {
      try {
        body = JSON.parse(init.body) as unknown;
      } catch {
        body = null;
      }
    }
    seen.push({
      url,
      method,
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
      body,
    });
    if (url === "/api/v1/routing/role" && method === "PUT") {
      const record = (body ?? {}) as Record<string, unknown>;
      const projectId = String(record["project_id"] ?? "");
      const role = String(record["role"] ?? "");
      const mode = String(record["mode"] ?? "");
      if (!FROZEN_ROLES.includes(role)) {
        return jsonBody({ error: `unknown role ${role}` }, 400);
      }
      if (mode !== "PINNED" && mode !== "pool" && mode !== "AUTO") {
        return jsonBody({ error: `unknown mode ${mode}` }, 400);
      }
      const row: Record<string, unknown> = {
        role,
        project_id: projectId,
        mode,
        provider: mode === "PINNED" ? (record["provider"] ?? null) : null,
        model: mode === "PINNED" ? (record["model"] ?? null) : null,
        binding: "DEFAULT",
        version: 1,
      };
      serverRows.set(rowKey(projectId, role), row);
      const answer: Record<string, unknown> = { ok: true, profile: row };
      if (role === "manager" && mode === "PINNED") {
        answer["manager_profile"] = {
          provider: row["provider"],
          model: row["model"],
          version: 1,
        };
      }
      return jsonBody(answer);
    }
    if (url.startsWith("/api/v1/routing/role?") && method === "GET") {
      const query = new URLSearchParams(url.split("?")[1] ?? "");
      const projectId = query.get("project_id") ?? "";
      const role = query.get("role") ?? "";
      if (!FROZEN_ROLES.includes(role)) {
        return jsonBody({ error: `unknown role ${role}` }, 400);
      }
      const row = serverRows.get(rowKey(projectId, role));
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
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = TOKEN;
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07http1 fixed manager PINNED round-trip", () => {
  it("proves manager PINNED PUT persists the fixed-manager fields and GET shows them", async () => {
    const shown = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RoleProfileEditor projectId="p-1" role="manager" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.providerLabel), {
      target: { value: "pa" },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modelLabel), {
      target: { value: "pa/m-1" },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modeLabel), {
      target: { value: "PINNED" },
    });
    await waitFor(() => {
      const row = serverRows.get(rowKey("p-1", "manager"));
      expect(row?.["mode"]).toBe("PINNED");
      expect(row?.["provider"]).toBe("pa");
      expect(row?.["model"]).toBe("pa/m-1");
    });
    const puts = seen.filter(
      (request) =>
        request.url === "/api/v1/routing/role" && request.method === "PUT",
    );
    expect(puts.length).toBeGreaterThanOrEqual(1);
    expect(puts[puts.length - 1].body).toMatchObject({
      project_id: "p-1",
      role: "manager",
      mode: "PINNED",
      provider: "pa",
      model: "pa/m-1",
    });
    for (const put of puts) {
      expect(put.headers["x-ui-session-token"]).toBe(TOKEN);
      expect(put.headers["x-actor"]).toBe("ui");
    }
    for (const request of seen) {
      expect(request.url).not.toContain("token");
    }
    shown.unmount();
    cleanup();
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RoleProfileEditor projectId="p-1" role="manager" />
      </ApiClientProvider>,
    );
    await screen.findByLabelText(en.settings.roleProfile.modeLabel);
    await waitFor(() => {
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
      ).toBe("PINNED");
      expect(
        (screen.getByLabelText(en.settings.roleProfile.providerLabel) as HTMLInputElement).value,
      ).toBe("pa");
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modelLabel) as HTMLInputElement).value,
      ).toBe("pa/m-1");
    });
  });
});
