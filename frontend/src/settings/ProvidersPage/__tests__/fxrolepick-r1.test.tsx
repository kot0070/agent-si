// FXROLEPICK R1: the real Providers page with Meta connected (fake at
// the network only) offers the connected enabled model in the setup
// wizard and in every role pool; pinning one saves through PUT
// /api/v1/roles/pools, and a refusal shows the server's own reason.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../../api/errors";
import { resetLocaleForTests, setLocale } from "../../../locale/index";
import { ProvidersPage } from "../ProvidersPage";

const META_MODELS = {
  provider_id: "meta",
  models: [
    {
      model: "meta/muse-spark-1.3-contributor",
      enabled: true,
      in_base: true,
      kb: null,
      id: "meta/muse-spark-1.3-contributor",
      name: "muse-spark-1.3-contributor",
      wire_id: "muse-spark-1.3-contributor",
      price: null,
      kb_known: true,
      listed: true,
    },
    {
      model: "meta/muse-spark-1.3",
      enabled: false,
      in_base: true,
      kb: null,
      id: "meta/muse-spark-1.3",
      name: "muse-spark-1.3",
      wire_id: "muse-spark-1.3",
      price: null,
      kb_known: true,
      listed: true,
    },
  ],
  source: "provider",
  enabled: ["meta/muse-spark-1.3-contributor"],
};

type SeenCall = { url: string; init: { method?: string; body?: string } };

function stubNetwork(putStatus: number, putBody: unknown): SeenCall[] {
  const calls: SeenCall[] = [];
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
        return json({ providers: [{ provider_id: "meta" }] });
      }
      if (url === "/api/v1/local/models") {
        return json([]);
      }
      if (url === "/api/v1/providers/meta/models") {
        return json(META_MODELS);
      }
      if (url.startsWith("/api/v1/roles/chat-model")) {
        return json({ project_id: "local", model_id: null });
      }
      if (url.startsWith("/api/v1/routing/role")) {
        return json({ error: "missing" }, 404);
      }
      if (url.startsWith("/api/v1/budget/providers/leftover-keys")) {
        return json({ entries: [] });
      }
      if (url === "/api/v1/roles/pools" && method === "PUT") {
        return json(putBody, putStatus);
      }
      return json({});
    }),
  );
  return calls;
}

function roleCard(role: string): HTMLElement {
  const section = screen.getByRole("region", { name: "Role pools" });
  const card = within(section)
    .getAllByTestId("role-pool-picker")
    .find((el) => el.getAttribute("data-role") === role);
  if (!card) {
    throw new Error(`role card missing: ${role}`);
  }
  return card;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  clearUiToken();
  setUiToken("r1-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R1 connected models in wizard and role pools", () => {
  it("offers the enabled model once and pins it through the save route", async () => {
    const calls = stubNetwork(200, { ok: true });
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByText("Show setup wizard"));
    const offered = await screen.findAllByText("Meta — muse-spark-1.3-contributor");
    expect(offered.length).toBeGreaterThanOrEqual(5);
    const setup = screen.getByRole("region", { name: "Setup" });
    const wizardBoxes = within(setup).getAllByRole("combobox");
    expect(wizardBoxes).toHaveLength(5);
    for (const box of wizardBoxes) {
      const texts = Array.from((box as HTMLSelectElement).options).map(
        (option) => option.textContent ?? "",
      );
      expect(texts).toContain("Meta — muse-spark-1.3-contributor");
      expect(
        texts.filter((text) => text === "Meta — muse-spark-1.3-contributor"),
      ).toHaveLength(1);
    }
    const director = roleCard("director");
    fireEvent.click(within(director).getByLabelText("Pinned model"));
    const select = within(director).getByLabelText(
      "Director pinned model",
    ) as HTMLSelectElement;
    const labels = Array.from(select.options).map(
      (option) => option.textContent ?? "",
    );
    expect(labels).toContain("Meta — muse-spark-1.3-contributor");
    expect(labels.filter((text) => text.includes("muse-spark-1.3-contributor"))).toHaveLength(1);
    fireEvent.change(select, { target: { value: select.options[1]?.value ?? "" } });
    expect(await screen.findByText("Saved Director.")).toBeTruthy();
    const puts = calls.filter(
      (call) => call.url === "/api/v1/roles/pools" && call.init.method === "PUT",
    );
    expect(puts.length).toBeGreaterThanOrEqual(1);
    const put = puts[puts.length - 1];
    const body = JSON.parse(put?.init.body as string) as Record<string, unknown>;
    expect(body).toMatchObject({
      project_id: "local",
      role: "director",
      mode: "PINNED",
      provider: "meta",
      model: "meta/muse-spark-1.3-contributor",
    });
  });

  it("a refusal shows the server's own reason in one sentence", async () => {
    stubNetwork(400, { error: "PINNED needs provider and model" });
    render(<ProvidersPage project_id="local" />);
    const director = roleCard("director");
    fireEvent.click(within(director).getByLabelText("Pinned model"));
    const select = within(director).getByLabelText(
      "Director pinned model",
    ) as HTMLSelectElement;
    // PLANB X2: the radio alone no longer saves; the model pick does.
    await waitFor(() => expect(select.options.length).toBeGreaterThan(1));
    fireEvent.change(select, { target: { value: select.options[1]?.value ?? "" } });
    await waitFor(() => {
      const text = screen.getByRole("status").textContent ?? "";
      expect(text).toContain("PINNED needs provider and model");
    });
  });
});
