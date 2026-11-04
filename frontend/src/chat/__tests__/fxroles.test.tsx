/** @vitest-environment jsdom */
// FXROLES: chat hierarchy rows (Director / Manager / Agents) plus the
// collapsed line over the REAL chat page. Only the fetch boundary answers
// here: GET /api/v1/providers names the connected providers, GET
// /api/v1/routing/role answers the saved role profiles, and PUT
// /api/v1/routing/role records the same body the Settings editors send
// (UI session token in the header) into an in-memory map the GET reads
// back, so a change in chat shows on the next read.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ChatArea } from "../index";
import { pt } from "../permissions";

const PROJECT_ID = "fxroles-p1";
const PROVIDERS_URL = "/api/v1/providers";
const ROLE_URL = "/api/v1/routing/role";
const SESSION_TOKEN = "fxroles-test-token";

type Profile = {
  mode: string;
  provider?: string;
  model?: string;
};

type SeenPut = {
  url: string;
  headers: Record<string, string>;
  body: unknown;
};

let connected: string[];
let profiles: Record<string, Profile>;
let puts: SeenPut[];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function profilePayload(role: string, profile: Profile): unknown {
  return {
    role,
    project_id: PROJECT_ID,
    mode: profile.mode,
    provider: profile.provider ?? null,
    model: profile.model ?? null,
    binding: "DEFAULT",
    version: 1,
  };
}

function readHeaders(init?: RequestInit): Record<string, string> {
  const raw = init?.headers;
  if (raw !== undefined && typeof raw === "object" && !(raw instanceof Headers)) {
    if (Array.isArray(raw)) {
      const out: Record<string, string> = {};
      for (const [key, value] of raw as Array<[string, string]>) {
        out[key] = value;
      }
      return out;
    }
    return { ...(raw as Record<string, string>) };
  }
  return {};
}

type ServedRow = { id: string; name: string; kb_known: boolean };

const MODEL_ROWS: Record<string, ServedRow[]> = {
  anthropic: [
    { id: "anthropic/claude-haiku-4-5", name: "claude-haiku-4-5", kb_known: true },
    { id: "anthropic/claude-haiku-5-5", name: "claude-haiku-5-5", kb_known: true },
  ],
  openai: [
    { id: "openai/gpt-4o-mini", name: "gpt-4o-mini", kb_known: true },
    { id: "openai/gpt-4o", name: "gpt-4o", kb_known: true },
  ],
};

function stubBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url === PROVIDERS_URL && method === "GET") {
      return jsonBody({
        providers: connected.map((provider_id) => ({ provider_id })),
      });
    }
    if (url.startsWith(ROLE_URL) && method === "GET") {
      const query = url.includes("?") ? url.split("?")[1] as string : "";
      const params = new URLSearchParams(query);
      const role = params.get("role") ?? "";
      const profile = profiles[role];
      if (profile === undefined) {
        return jsonBody({ error: "missing" }, 404);
      }
      return jsonBody({ profile: profilePayload(role, profile) });
    }
    if (url === ROLE_URL && method === "PUT") {
      let body: Record<string, unknown> = {};
      try {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      } catch {
        body = {};
      }
      puts.push({ url, headers: readHeaders(init), body });
      const role = typeof body.role === "string" ? body.role : "";
      const next: Profile = {
        mode: typeof body.mode === "string" ? body.mode : "AUTO",
      };
      if (typeof body.provider === "string") {
        next.provider = body.provider;
      }
      if (typeof body.model === "string") {
        next.model = body.model;
      }
      profiles[role] = next;
      return jsonBody({ ok: true, profile: profilePayload(role, next) });
    }
    const modelsMatch = url.match(/^\/api\/v1\/providers\/([^/]+)\/models$/);
    if (modelsMatch !== null && method === "GET") {
      const id = modelsMatch[1] as string;
      const rows = MODEL_ROWS[id] ?? [];
      return jsonBody({
        provider_id: id,
        models: rows,
        source: "provider",
        enabled: rows.map((row) => row.id),
      });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

function seedProfiles(next: Record<string, Profile>): void {
  profiles = { ...next };
}

function defaultSeed(): void {
  seedProfiles({
    director: { mode: "PINNED", provider: "anthropic", model: "anthropic/claude-haiku-5-5" },
    manager: { mode: "AUTO" },
    worker: { mode: "PINNED", provider: "openai", model: "openai/gpt-4o-mini" },
    auditor: { mode: "PINNED", provider: "openai", model: "openai/gpt-4o-mini" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  clearUiToken();
  setUiToken(SESSION_TOKEN);
  connected = ["anthropic", "openai"];
  puts = [];
  defaultSeed();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderChat(projectId: string = PROJECT_ID): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <ChatArea projectId={projectId} />
    </ApiClientProvider>,
  );
}

async function expandRows(): Promise<void> {
  fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
  expect(await screen.findByTestId("hierarchy-row-director")).toBeTruthy();
}

describe("fxroles chat hierarchy rows", () => {
  it("expands the collapsed line into the Director, Manager and Agents rows", async () => {
    renderChat();
    expect(await screen.findByTestId("hierarchy-collapsed")).toBeTruthy();
    expect(screen.queryByTestId("hierarchy-row-director")).toBeNull();
    await expandRows();
    expect(await screen.findByTestId("hierarchy-row-manager")).toBeTruthy();
    expect(await screen.findByTestId("hierarchy-row-agents")).toBeTruthy();
  });

  it("collapsed line reads the saved values and remembers the expansion", async () => {
    renderChat();
    expect(await screen.findByTestId("hierarchy-collapsed")).toBeTruthy();
    await expandRows();
    fireEvent.click(await screen.findByTestId("hierarchy-collapse"));
    expect(await screen.findByTestId("hierarchy-collapsed")).toBeTruthy();
    // D6A: the collapsed summary renders one span per locale value with
    // the ": " and middle-dot dividers as CSS (locale-only contract), so
    // textContent concatenates without them. Same asserted values+order
    // as before; visual text is unchanged (separators come from CSS).
    expect(
      (await screen.findByTestId("hierarchy-collapsed")).textContent,
    ).toBe(
      "DirectorAnthropic \u2014 AdvancedManagerAutoAgentsOpenAI \u2014 Standard",
    );
    fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
    expect(await screen.findByTestId("hierarchy-row-director")).toBeTruthy();
    cleanup();
    renderChat();
    expect(await screen.findByTestId("hierarchy-row-director")).toBeTruthy();
    expect(screen.queryByTestId("hierarchy-collapsed")).toBeNull();
  });

  it("Manager to Anthropic sends the Settings PUT with the session token", async () => {
    renderChat();
    await expandRows();
    const target = screen.getByTestId("hierarchy-select-manager");
    fireEvent.change(target, {
      target: { value: "anthropic/claude-haiku-4-5" },
    });
    await waitFor(() => {
      expect(puts.length).toBeGreaterThanOrEqual(1);
    });
    const put = puts[puts.length - 1] as SeenPut;
    expect(put.url).toBe(ROLE_URL);
    expect(put.body).toEqual({
      project_id: PROJECT_ID,
      role: "manager",
      mode: "PINNED",
      provider: "anthropic",
      model: "anthropic/claude-haiku-4-5",
    });
    expect(put.headers["x-ui-session-token"]).toBe(SESSION_TOKEN);
    await waitFor(() => {
      expect(
        (screen.getByTestId("hierarchy-select-manager") as HTMLSelectElement).value,
      ).toBe("anthropic/claude-haiku-4-5");
    });
  });

  it("Agents row saves worker and auditor together", async () => {
    seedProfiles({
      director: { mode: "AUTO" },
      manager: { mode: "AUTO" },
      worker: { mode: "AUTO" },
      auditor: { mode: "AUTO" },
    });
    renderChat();
    await expandRows();
    fireEvent.change(await screen.findByTestId("hierarchy-select-agents"), {
      target: { value: "openai/gpt-4o-mini" },
    });
    await waitFor(() => {
      expect(puts.length).toBeGreaterThanOrEqual(2);
    });
    const roles = puts.map((put) => (put.body as { role?: unknown }).role);
    expect(roles).toEqual(["worker", "auditor"]);
    for (const put of puts) {
      expect(put.body).toMatchObject({
        project_id: PROJECT_ID,
        mode: "PINNED",
        provider: "openai",
        model: "openai/gpt-4o-mini",
      });
      expect(put.headers["x-ui-session-token"]).toBe(SESSION_TOKEN);
    }
  });

  it("no connected provider shows the Connect link and no empty list", async () => {
    connected = [];
    renderChat();
    await expandRows();
    expect(screen.queryByTestId("hierarchy-select-director")).toBeNull();
    expect(screen.queryByTestId("hierarchy-select-manager")).toBeNull();
    expect(screen.queryByTestId("hierarchy-select-agents")).toBeNull();
    const links = screen.getAllByTestId("hierarchy-connect-link");
    expect(links.length).toBeGreaterThanOrEqual(1);
    for (const link of links) {
      expect(link.getAttribute("href")).toBe("/settings/models");
    }
  });

  it("split auditor shows the words plus the Settings link", async () => {
    seedProfiles({
      director: { mode: "AUTO" },
      manager: { mode: "AUTO" },
      worker: { mode: "PINNED", provider: "openai", model: "openai/gpt-4o-mini" },
      auditor: { mode: "PINNED", provider: "anthropic", model: "anthropic/claude-haiku-5-5" },
    });
    renderChat();
    await expandRows();
    const row = await screen.findByTestId("hierarchy-row-agents");
    const note = within(row).getByTestId("hierarchy-auditor-split");
    expect(note.textContent).toContain("different");
    const link = within(row).getByTestId("hierarchy-settings-link");
    expect(link.getAttribute("href")).toBe("/settings/routing");
  });

  it("no current project asks to choose a project", async () => {
    renderChat("");
    expect(await screen.findByTestId("hierarchy-no-project")).toBeTruthy();
    expect(screen.queryByTestId("hierarchy-collapsed")).toBeNull();
    expect(screen.queryByTestId("hierarchy-row-director")).toBeNull();
  });

  it("English defaults survive when the locale table lacks the new keys", async () => {
    setLocale("uk");
    renderChat();
    expect(await screen.findByTestId("hierarchy-collapsed")).toBeTruthy();
    await expandRows();
    const row = await screen.findByTestId("hierarchy-row-director");
    expect(row.textContent).toContain(
      pt("chat.hierarchy.director", "Director"),
    );
    expect((await screen.findByTestId("hierarchy-row-manager")).textContent).toContain(
      pt("chat.hierarchy.manager", "Manager"),
    );
    expect((await screen.findByTestId("hierarchy-row-agents")).textContent).toContain(
      pt("chat.hierarchy.agents", "Agents"),
    );
  });
});
