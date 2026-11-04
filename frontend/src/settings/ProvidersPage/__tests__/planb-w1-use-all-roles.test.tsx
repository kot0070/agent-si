// PLANB W1: Settings -> Local LLM "Use for agents" pins the chosen local
// model on Director, Manager, Worker and Auditor through the role-pool
// route, then the card reads the roles back and shows each role's model.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../../api/errors";
import { resetLocaleForTests, setLocale } from "../../../locale/index";
import { LocalConnectSection } from "../LocalConnectSection";

const GLIMMER = {
  provider_id: "ollama",
  models: [
    { id: "ollama/muse-glimmer:30b", name: "muse-glimmer:30b", price: null, kb_known: true },
  ],
  source: "local",
  enabled: [],
};

type SeenCall = { url: string; init: { method?: string; body?: string } };

function stubNetwork(): { calls: SeenCall[]; saved: Record<string, string> } {
  const calls: SeenCall[] = [];
  const saved: Record<string, string> = {};
  const json = (data: unknown, status = 200): Response =>
    new Response(JSON.stringify(data), {
      status,
      headers: { "content-type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, init: { method, body: String(init?.body ?? "") } });
      if (url === "/api/v1/providers") {
        return json({ providers: [] });
      }
      if (url.startsWith("/api/v1/local/bench/check")) {
        const endpoint = new URL(url, "http://x").searchParams.get("endpoint") ?? "";
        return json({ reachable: endpoint.includes("11434"), reason: "open" });
      }
      if (url === "/api/v1/local/models") {
        return json([
          { model: "http://localhost:11434", evidence_tier: "PROXY", status: "READY" },
        ]);
      }
      if (url === "/api/v1/providers/ollama/models") {
        return json(GLIMMER);
      }
      if (url === "/api/v1/roles/pools" && method === "PUT") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { role: string; model: string };
        saved[body.role] = body.model;
        return json({ ok: true });
      }
      if (url.startsWith("/api/v1/roles/pools?") && method === "GET") {
        return json({
          roles: ["director", "manager", "worker", "auditor", "watcher"].map((role) => ({
            role,
            mode: role in saved ? "PINNED" : "AUTO",
            provider: role in saved ? "ollama" : null,
            model: saved[role] ?? null,
            pool: [],
            strategy: "AUTO",
          })),
        });
      }
      return json({});
    }),
  );
  return { calls, saved };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  clearUiToken();
  setUiToken("w1-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("PLANB W1 use for agents", () => {
  it("pins four roles and shows each role on the model", async () => {
    const { calls } = stubNetwork();
    render(<LocalConnectSection />);
    const card = await screen.findByTestId("local-preset-ollama");
    await within(card).findByTestId("local-models-ollama");
    fireEvent.click(within(card).getByTestId("local-use-ollama"));
    const list = await within(card).findByTestId("local-roles-ollama");
    const puts = calls
      .filter((call) => call.url === "/api/v1/roles/pools" && call.init.method === "PUT")
      .map((call) => JSON.parse(call.init.body as string));
    expect(puts.map((body) => body.role).sort()).toEqual(
      ["auditor", "director", "manager", "worker"],
    );
    for (const body of puts) {
      expect(body).toMatchObject({
        project_id: "local",
        mode: "PINNED",
        provider: "ollama",
        model: "ollama/muse-glimmer:30b",
      });
    }
    for (const role of ["Director", "Manager", "Worker", "Auditor"]) {
      const row = within(list).getByText(new RegExp(`^${role}`));
      expect(row.textContent).toContain("muse-glimmer:30b");
    }
    expect(list.textContent).not.toContain("Watcher");
  });

  it("uk labels", async () => {
    setLocale("uk");
    stubNetwork();
    render(<LocalConnectSection />);
    const card = await screen.findByTestId("local-preset-ollama");
    await within(card).findByTestId("local-models-ollama");
    fireEvent.click(within(card).getByTestId("local-use-ollama"));
    const list = await within(card).findByTestId("local-roles-ollama");
    expect(list.textContent).toContain("Директор");
    expect(list.textContent).toContain("Аудитор");
    expect(list.textContent).toContain("muse-glimmer:30b");
  });
});
