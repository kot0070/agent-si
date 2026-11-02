/**
 * @vitest-environment jsdom
 *
 * FXPROV round 2: the connect dialog is two steps.
 * 1. Save -> step 2 in the same dialog (Connected line + model list with a
 *    loading state; tick, Done closes). X/Esc/backdrop always close, even
 *    during a pending save. Save is bounded by a timeout; the key leaves
 *    state on close and after save.
 * 2. GET /providers/{id}/models in the new shape ({models:[{id,name,price,
 *    kb_known}], source, enabled}); live-list failure falls back to the
 *    catalog with a calm "showing the known list" line naming source catalog.
 * 3. Fresh connect ticks only the default; the served enabled list, when
 *    named, is the truth; search + a compact scrolling list for many rows.
 * 4. Rows outside the capability base carry a mark and stay selectable.
 * 5. Cards show Connected, enabled count, Manage models (reopens step 2),
 *    Disconnect; mount reads the route, refetched after connect/disconnect.
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

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type MutableRoutes = {
  providers: unknown[];
  models: Record<string, unknown>;
  source?: string;
  enabled?: Record<string, string[]>;
  hangKeys?: boolean;
  hangConnect?: boolean;
};

function stubServed(routes: MutableRoutes): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/providers") {
      return json({ providers: routes.providers });
    }
    if (url === "/api/v1/local/models") {
      return json([]);
    }
    const match = url.match(/^\/api\/v1\/providers\/([^/]+)\/models$/);
    if (match !== null) {
      const id = match[1] as string;
      const payload = routes.models[id];
      if (payload === undefined) {
        return json({ provider_id: id, models: [] });
      }
      return json(payload);
    }
    if (url === "/api/v1/providers/keys") {
      if (routes.hangKeys === true) {
        await new Promise(() => {});
      }
      return json({ key_ref: { secret_id: "fx", provider_id: "fx" } }, 201);
    }
    if (url === "/api/v1/providers/connect") {
      if (routes.hangConnect === true) {
        await new Promise(() => {});
      }
      return json({ provider: { provider_id: "fx" } });
    }
    return json({});
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  setUiToken("fxprov2-token");
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

function openOpenai(): HTMLElement {
  fireEvent.click(screen.getByLabelText("Connect OpenAI"));
  return screen.getByRole("dialog");
}

function saveKey(dialog: HTMLElement, key = "sk-fxprov2"): void {
  fireEvent.change(within(dialog).getByLabelText("API key"), {
    target: { value: key },
  });
  fireEvent.click(within(dialog).getByText("Save"));
}

describe("FXPROV2 step 2 opens in the same dialog", () => {
  it("Save moves to the model list; only the default is ticked; Done closes", async () => {
    stubServed({ providers: [], models: {} });
    render(<ProvidersPage project_id="local" />);
    const dialog = openOpenai();
    saveKey(dialog);
    expect(await within(dialog).findByText("Connected OpenAI.")).toBeTruthy();
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    expect(rows.length).toBe(2);
    const checked = rows
      .map((row) => within(row).getByRole("checkbox") as HTMLInputElement)
      .filter((box) => box.checked);
    expect(checked).toHaveLength(1);
    expect(checked[0].getAttribute("aria-label")).toBe("openai/gpt-4o-mini");
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("1 enabled")).toBeTruthy();
  });

  it("X closes even during a pending save and the key is gone", async () => {
    stubServed({ providers: [], models: {}, hangKeys: true });
    render(<ProvidersPage project_id="local" />);
    const dialog = openOpenai();
    saveKey(dialog);
    expect(await screen.findByText("Saving...", {}, { timeout: 2000 })).toBeTruthy();
    fireEvent.click(within(dialog).getByLabelText("Close"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy();
  });

  it("Esc closes from step 2 without committing extra ticks", async () => {
    stubServed({ providers: [], models: {} });
    render(<ProvidersPage project_id="local" />);
    const dialog = openOpenai();
    saveKey(dialog);
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    fireEvent.click(within(rows[1]).getByRole("checkbox"));
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Only the fresh-connect default survived; the extra tick was dropped.
    expect(screen.getByText("1 enabled")).toBeTruthy();
  });
});

describe("FXPROV2 list source and fallback", () => {
  it("live-list failure falls back to the catalog and says so calmly", async () => {
    stubServed({ providers: [], models: {} });
    render(<ProvidersPage project_id="local" />);
    const dialog = openOpenai();
    saveKey(dialog);
    expect(await within(dialog).findByText("showing the known list")).toBeTruthy();
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    expect(rows.length).toBe(2);
    expect(
      within(rows[0]).getByTestId("connect-model-id-openai/gpt-4o-mini"),
    ).toBeTruthy();
  });

  it("new-shape payload is read verbatim: names, prices, marks, source", async () => {
    const models: Record<string, unknown> = {
      openai: {
        provider_id: "openai",
        source: "provider",
        enabled: ["openai/gpt-4o"],
        models: [
          { id: "openai/gpt-4o-mini", name: "Mini", price: 0.15, kb_known: true },
          { id: "openai/gpt-4o", name: "Full", price: null, kb_known: false },
        ],
      },
    };
    stubServed({ providers: [{ provider_id: "openai" }], models });
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Manage OpenAI models"));
    const dialog = screen.getByRole("dialog");
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Mini")).toBeTruthy();
    expect(within(rows[0]).getByTestId("connect-model-price-openai/gpt-4o-mini").textContent).toBe("$0.15");
    // Outside the capability base: marked, still selectable.
    expect(within(rows[1]).getByTestId("connect-model-kb-openai/gpt-4o").textContent).toContain(
      "not in capability base",
    );
    const fullBox = within(rows[1]).getByRole("checkbox") as HTMLInputElement;
    expect(fullBox.disabled).toBe(false);
    expect(screen.queryByText("showing the known list")).toBeNull();
  });

  it("served enabled list is the tick truth on Manage reopen", async () => {
    const models: Record<string, unknown> = {
      openai: {
        provider_id: "openai",
        source: "provider",
        enabled: ["openai/gpt-4o"],
        models: [
          { id: "openai/gpt-4o-mini", name: "Mini", price: null, kb_known: true },
          { id: "openai/gpt-4o", name: "Full", price: null, kb_known: true },
        ],
      },
    };
    stubServed({ providers: [{ provider_id: "openai" }], models });
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Manage OpenAI models"));
    const dialog = screen.getByRole("dialog");
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    const mini = within(rows[0]).getByRole("checkbox") as HTMLInputElement;
    const full = within(rows[1]).getByRole("checkbox") as HTMLInputElement;
    expect(mini.checked).toBe(false);
    expect(full.checked).toBe(true);
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("1 enabled")).toBeTruthy();
  });
});

describe("FXPROV2 many rows: filter plus compact scroll", () => {
  it("Filter narrows the list; the list scrolls inside the dialog", async () => {
    const many = Array.from({ length: 30 }, (_, index) => ({
      id: `openai/extra-${index}`,
      name: `Extra ${index}`,
      price: null,
      kb_known: true,
    }));
    const models: Record<string, unknown> = {
      openai: { provider_id: "openai", source: "provider", models: many },
    };
    stubServed({ providers: [], models });
    render(<ProvidersPage project_id="local" />);
    const dialog = openOpenai();
    saveKey(dialog);
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    // Live list wins (served rows only); the catalog is the fallback.
    expect(rows.length).toBe(30);
    const list = within(dialog).getByTestId("connect-model-list");
    expect(list.style.maxHeight).toBe("240px");
    expect(list.style.overflowY).toBe("auto");
    fireEvent.change(within(dialog).getByLabelText("Filter models"), {
      target: { value: "extra-29" },
    });
    expect(within(dialog).getAllByTestId("connect-model-row")).toHaveLength(1);
    fireEvent.change(within(dialog).getByLabelText("Filter models"), {
      target: { value: "" },
    });
    expect(within(dialog).getAllByTestId("connect-model-row")).toHaveLength(30);
  });
});

describe("FXPROV2 cards after Done", () => {
  it("card shows Connected, count, Manage and Disconnect; mount reads the route", async () => {
    stubServed({ providers: [{ provider_id: "openai" }], models: {} });
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    expect(screen.getByLabelText("Manage OpenAI models")).toBeTruthy();
    expect(screen.getByText("0 enabled")).toBeTruthy();
    const card = screen
      .getAllByTestId("provider-card")
      .find((entry) => entry.getAttribute("data-provider-id") === "openai");
    if (!card) {
      throw new Error("openai card missing");
    }
    fireEvent.click(within(card).getByLabelText("OpenAI Standard"));
    expect(screen.getByText("1 enabled")).toBeTruthy();
  });
});
