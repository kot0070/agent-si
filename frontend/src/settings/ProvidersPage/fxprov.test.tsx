/**
 * @vitest-environment jsdom
 *
 * FXPROV: provider settings behave against the served state.
 * P1: a good save closes the dialog by itself; the card shows Disconnect
 *   plus the quiet Connected line; Save stays disabled on an empty key.
 * P2: served state is the truth on remount (leave/return) and after restart
 *   (fresh served registry lists nothing); local runtimes map back from
 *   GET /api/v1/local/models by base URL; unknown served ids are ignored.
 * P3: a connected provider lists the union of the served provider listing
 *   (GET /api/v1/providers/{id}/models) and the KB-derived catalog, in that
 *   order, with id + price-or-"not known" + toggle; search, role pickers,
 *   the chat picker and setup read the same merged list.
 * P4: the modal has quiet X/Cancel, one primary Save, id+type+url on one
 *   quiet line, width <= 560, and an opaque backdrop.
 * P5: the L3 row is label, model id in <small>, toggle beside the id.
 * Network is the only fake (global fetch); no component doubles.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";
import { modelPriceText, mergeModelList } from "./modelsApi";

const FX_TOKEN = "fxprov-token-01";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type MutableRoutes = {
  providers: unknown[];
  models: Record<string, unknown[]>;
  localModels: unknown[];
};

function stubServed(routes: MutableRoutes): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/providers") {
      return json({ providers: routes.providers });
    }
    if (url === "/api/v1/local/models") {
      return json(routes.localModels);
    }
    const match = url.match(/^\/api\/v1\/providers\/([^/]+)\/models$/);
    if (match !== null) {
      return json({ provider_id: match[1], models: routes.models[match[1] as string] ?? [] });
    }
    if (url === "/api/v1/providers/keys") {
      return json({ key_ref: { secret_id: "fx", provider_id: "fx" } }, 201);
    }
    if (url === "/api/v1/providers/connect") {
      return json({ provider: { provider_id: "fx" } });
    }
    if (url === "/api/v1/local/connect") {
      return json({ status: "NOT_CONFIGURED", reason: "attached" });
    }
    return json({});
  });
}

function emptyRoutes(): MutableRoutes {
  return { providers: [], models: {}, localModels: [] };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  setUiToken(FX_TOKEN);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function openaiCard(): HTMLElement {
  const card = screen
    .getAllByTestId("provider-card")
    .find((entry) => entry.getAttribute("data-provider-id") === "openai");
  if (!card) {
    throw new Error("openai card missing");
  }
  return card;
}

describe("FXPROV P1 save moves to step 2 in the same dialog", () => {
  it("Save shows Connected + model list; Done closes; card keeps quiet line", async () => {
    stubServed(emptyRoutes());
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const dialog = screen.getByRole("dialog");
    expect(
      (within(dialog).getByText("Save") as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "sk-fxprov" },
    });
    fireEvent.click(within(dialog).getByText("Save"));
    // Step 2 in the same dialog: Connected line, tickable list, key gone.
    expect(await within(dialog).findByText("Connected OpenAI. Reference saved.")).toBeTruthy();
    expect(screen.queryByLabelText("API key")).toBeNull();
    // Fresh connect ticks only the default model, never everything.
    const ticks = within(dialog).getAllByRole("checkbox") as HTMLInputElement[];
    expect(ticks.length).toBeGreaterThan(1);
    expect(ticks.filter((box) => box.checked).map((box) => box.getAttribute("aria-label"))).toEqual([
      "OpenAI Standard",
    ]);
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByLabelText("Disconnect OpenAI")).toBeTruthy();
    expect(screen.getByText("Connected OpenAI. Reference saved.")).toBeTruthy();
    expect(screen.getByText("1 enabled")).toBeTruthy();
  });
});

describe("FXPROV P2 served state is the truth", () => {
  it("leave and return keeps Disconnect from the served GET alone", async () => {
    const routes = emptyRoutes();
    routes.providers = [
      { provider_id: "openai", type: "cloud", base_url: "https://api.openai.com/v1" },
    ];
    stubServed(routes);
    const first = render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    first.unmount();
    cleanup();
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
  });

  it("restart (fresh served registry) shows Connect again", async () => {
    const routes = emptyRoutes();
    routes.providers = [{ provider_id: "openai" }];
    stubServed(routes);
    const first = render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    first.unmount();
    cleanup();
    // Fresh process, empty registry: served truth is disconnected.
    routes.providers = [];
    render(<ProvidersPage project_id="local" />);
    await waitFor(() =>
      expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy(),
    );
    expect(screen.queryByLabelText("Disconnect OpenAI")).toBeNull();
  });

  it("attached local runtime connects the matching local card", async () => {
    const routes = emptyRoutes();
    routes.localModels = [
      { model: "http://localhost:11434", evidence_tier: "proxy", status: "READY" },
    ];
    stubServed(routes);
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect Ollama")).toBeTruthy();
    expect(screen.getByLabelText("Connect LM Studio")).toBeTruthy();
  });

  it("unknown served ids never disturb the cards", async () => {
    const routes = emptyRoutes();
    routes.providers = [{ provider_id: "no-such-provider" }];
    stubServed(routes);
    render(<ProvidersPage project_id="local" />);
    await waitFor(() =>
      expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy(),
    );
    expect(screen.queryByLabelText("Disconnect OpenAI")).toBeNull();
  });
});

describe("FXPROV P3 merged model list", () => {
  it("served ids merge over the catalog with id, price-or-not-known and toggle", async () => {
    const routes = emptyRoutes();
    routes.providers = [{ provider_id: "openai" }];
    routes.models["openai"] = [
      { model: "gpt-4o-mini", enabled: true, in_base: true, kb: null },
      {
        model: "served-extra",
        enabled: true,
        in_base: true,
        kb: {
          fields: {
            input_token_price: { value: 2.5 },
            output_token_price: { value: 10 },
          },
        },
      },
    ];
    stubServed(routes);
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    const card = openaiCard();
    const rows = within(card).getAllByTestId("model-row");
    // Served first (bare mini joined to its qualified catalog entry, then
    // the genuine served extra), then catalog-only Advanced; no duplicates,
    // nothing invented.
    const ids = rows.map(
      (row) => within(row).getByTestId(/model-id-/).textContent,
    );
    expect(ids).toContain("openai/gpt-4o-mini");
    expect(ids).toContain("served-extra");
    expect(ids).toContain("openai/gpt-4o");
    expect(new Set(ids).size).toBe(ids.length);
    expect(
      within(card).getByTestId("model-price-openai/gpt-4o-mini").textContent,
    ).toBe("not known");
    expect(
      within(card).getByTestId("model-price-served-extra").textContent,
    ).toBe("$2.5/$10");
    // The served-only toggle works and feeds the pickers by label.
    fireEvent.click(within(card).getByLabelText("OpenAI served-extra"));
    expect(
      (within(card).getByLabelText("OpenAI served-extra") as HTMLInputElement).checked,
    ).toBe(true);
    const chat = screen.getByTestId("chat-model-selector");
    const chatSelect = within(chat).getByLabelText("Chat model") as HTMLSelectElement;
    const chatLabels = Array.from(chatSelect.options)
      .map((option) => option.textContent ?? "")
      .join(" | ");
    expect(chatLabels).toContain("served-extra");
  });

  it("search matches served ids; role pickers read the same list", async () => {
    const routes = emptyRoutes();
    routes.providers = [{ provider_id: "openai" }];
    routes.models["openai"] = [
      { model: "served-extra", enabled: true, in_base: true, kb: null },
    ];
    stubServed(routes);
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    const card = openaiCard();
    fireEvent.click(within(card).getByLabelText("OpenAI served-extra"));
    fireEvent.change(screen.getByLabelText("Search models"), {
      target: { value: "served-extra" },
    });
    // Search filters cards over the merged list: the OpenAI card (which
    // owns the served id) stays with all its rows; other cards hide.
    expect(within(card).getByTestId("model-id-served-extra")).toBeTruthy();
    expect(screen.getByLabelText("Disconnect OpenAI")).toBeTruthy();
    expect(screen.queryByLabelText("Connect Meta")).toBeNull();
    fireEvent.change(screen.getByLabelText("Search models"), {
      target: { value: "zzz-no-such-model" },
    });
    expect(screen.queryAllByTestId("model-row")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Search models"), { target: { value: "" } });
    const worker = screen
      .getAllByTestId("role-pool-picker")
      .find((entry) => entry.getAttribute("data-role") === "worker");
    if (!worker) {
      throw new Error("worker picker missing");
    }
    fireEvent.click(within(worker).getByLabelText("Pinned model"));
    const select = within(worker).getByLabelText("Worker pinned model") as HTMLSelectElement;
    const labels = Array.from(select.options)
      .map((option) => option.textContent ?? "")
      .join(" | ");
    expect(labels).toContain("served-extra");
  });

  it("modelPriceText and mergeModelList are honest about sources", () => {
    expect(modelPriceText(null)).toBe("not known");
    expect(modelPriceText({})).toBe("not known");
    expect(
      modelPriceText({ input_token_price: 1, output_token_price: 4 }),
    ).toBe("$1/$4");
    const merged = mergeModelList(
      [{ id: "openai/gpt-4o-mini", label: "Standard" }],
      [
        { model: "gpt-4o-mini", enabled: true, in_base: true, kb: null },
        { model: "fresh", enabled: true, in_base: true, kb: null },
      ],
      "openai",
    );
    expect(merged.map((entry) => entry.id)).toEqual([
      "openai/gpt-4o-mini",
      "fresh",
    ]);
    expect(merged[0].label).toBe("Standard");
    expect(merged[1].label).toBe("fresh");
  });
});

describe("FXPROV P4 modal shape", () => {
  it("quiet X/Cancel, one primary Save, one quiet id line, narrow opaque overlay", () => {
    stubServed(emptyRoutes());
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const backdrop = screen.getByTestId("connect-backdrop");
    expect(backdrop.contains(dialog)).toBe(true);
    expect(getComputedStyle(backdrop).backgroundColor).toBe("rgb(0, 0, 0)");
    const dialogBox = dialog as HTMLElement;
    expect(dialogBox.style.maxWidth).toBe("480px");
    expect(Number.parseInt(dialogBox.style.maxWidth, 10)).toBeLessThanOrEqual(560);
    expect(within(dialog).getByText("Save").getAttribute("data-variant")).toBe("primary");
    expect(within(dialog).getByText("Cancel").getAttribute("data-variant")).toBe("quiet");
    expect(within(dialog).getByLabelText("Close").getAttribute("data-variant")).toBe("quiet");
    // Provider ID + Type + Base URL share one quiet line.
    const idLine = within(dialog).getByText("openai").closest("p");
    expect(idLine).toBeTruthy();
    expect(idLine?.getAttribute("data-variant")).toBe("quiet");
    expect(idLine?.textContent).toContain("cloud");
    expect(idLine?.textContent).toContain("https://api.openai.com/v1");
  });
});

describe("FXPROV P5 L3 row", () => {
  it("label, small id, toggle beside the id; disabled explains itself", () => {
    stubServed(emptyRoutes());
    render(<ProvidersPage project_id="local" />);
    const card = openaiCard();
    const row = within(card)
      .getAllByTestId("model-row")
      .find((entry) =>
        entry.textContent?.includes("openai/gpt-4o-mini"),
      );
    if (!row) {
      throw new Error("openai mini row missing");
    }
    const idCell = within(row).getByTestId("model-id-openai/gpt-4o-mini");
    expect(idCell.tagName.toLowerCase()).toBe("small");
    const box = within(row).getByLabelText("OpenAI Standard") as HTMLInputElement;
    expect(box.disabled).toBe(true);
    expect(box.title.length).toBeGreaterThan(0);
    // The toggle sits beside the small id, not wrapped in its label.
    const position = idCell.compareDocumentPosition(box);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(row.querySelector("label")).toBeNull();
  });
});
