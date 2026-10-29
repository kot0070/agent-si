/** @vitest-environment jsdom */
// K07HTTP1 BP06-6: two roles times two projects isolation over the
// server, driven through the REAL RoleProfileEditor over a fresh
// HttpApiClient (only global fetch stubbed; no FakeApiClient). The stub
// mirrors the backend set_role/get_role shapes
// (src/agent_si/backend/pools_routes.py:359 write with the :96
// _profile_payload shape, :343 read with 404 for a missing row); every
// row is keyed one row per role per project.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { RoleProfileEditor } from "../index";
import { readRoleProfilesFromServer } from "../roleProfilesApi";
import en from "../../locale/en.json";

const TOKEN = "tok-k07-per-role-project";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const FROZEN_ROLES = ["director", "manager", "worker", "auditor", "watcher"];

const serverRows = new Map<string, Record<string, unknown>>();

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
      return jsonBody({ ok: true, profile: row });
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

async function saveViaEditor(
  projectId: string,
  role: string,
  mode: string,
  provider: string,
  model: string,
): Promise<void> {
  const shown = render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RoleProfileEditor projectId={projectId} role={role} />
    </ApiClientProvider>,
  );
  if (provider.length > 0) {
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.providerLabel), {
      target: { value: provider },
    });
  }
  if (model.length > 0) {
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modelLabel), {
      target: { value: model },
    });
  }
  fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modeLabel), {
    target: { value: mode },
  });
  await waitFor(() => {
    const row = serverRows.get(rowKey(projectId, role));
    expect(row?.["mode"]).toBe(mode);
    if (mode === "PINNED") {
      expect(row?.["provider"]).toBe(provider);
      expect(row?.["model"]).toBe(model);
    }
  });
  shown.unmount();
  cleanup();
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

describe("k07http1 role profiles per role per project", () => {
  it("proves two roles times two projects isolation over the server", async () => {
    await saveViaEditor("p-a", "worker", "PINNED", "pa", "pa/wa-1");
    await saveViaEditor("p-a", "manager", "PINNED", "pa", "pa/ma-1");
    await saveViaEditor("p-b", "worker", "PINNED", "pb", "pb/wb-1");
    await saveViaEditor("p-b", "manager", "pool", "", "");
    const mapA = await readRoleProfilesFromServer("p-a");
    expect(mapA["worker"]).toEqual({
      mode: "PINNED",
      provider: "pa",
      model: "pa/wa-1",
    });
    expect(mapA["manager"]).toEqual({
      mode: "PINNED",
      provider: "pa",
      model: "pa/ma-1",
    });
    const mapB = await readRoleProfilesFromServer("p-b");
    expect(mapB["worker"]).toEqual({
      mode: "PINNED",
      provider: "pb",
      model: "pb/wb-1",
    });
    expect(mapB["manager"]).toEqual({ mode: "pool" });
    expect(Object.keys(mapA).sort()).toEqual(["manager", "worker"]);
    expect(Object.keys(mapB).sort()).toEqual(["manager", "worker"]);
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RoleProfileEditor projectId="p-b" role="worker" />
      </ApiClientProvider>,
    );
    await screen.findByLabelText(en.settings.roleProfile.modeLabel);
    await waitFor(() => {
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
      ).toBe("PINNED");
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modelLabel) as HTMLInputElement).value,
      ).toBe("pb/wb-1");
    });
  });
});
