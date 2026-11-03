/** @vitest-environment jsdom */
// FXLOOK D4 RED: a served-connected provider never reads "None enabled"
// while runs work — the card names the connection and the model; model
// rows with no price fold behind Show all. Network is the only fake.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";

const FX_TOKEN = "fxlook-d4-token";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type MutableRoutes = {
  providers: unknown[];
  models: Record<string, unknown>;
};

function stubServed(routes: MutableRoutes): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/providers") {
      return json({ providers: routes.providers });
    }
    const match = url.match(/^\/api\/v1\/providers\/([^/]+)\/models$/);
    if (match !== null) {
      return json(routes.models[match[1] as string] ?? { models: [] });
    }
    return json({});
  });
}

function cardFor(id: string): HTMLElement {
  const card = screen
    .getAllByTestId("provider-card")
    .find((entry) => entry.getAttribute("data-provider-id") === id);
  if (!card) {
    throw new Error(`${id} card missing`);
  }
  return card;
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

describe("FXLOOK D4 connected card names connection and model", () => {
  it("Meta connected with served ticks reads Meta connected · model", async () => {
    stubServed({
      providers: [{ provider_id: "meta" }],
      models: {
        meta: {
          provider_id: "meta",
          source: "provider",
          enabled: ["meta/muse-spark-1.3-contributor"],
          models: [
            {
              model: "muse-spark-1.3-contributor",
              enabled: true,
              in_base: true,
              kb: null,
            },
          ],
        },
      },
    });
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect Meta")).toBeTruthy();
    const card = cardFor("meta");
    // The served routing truth is adopted: the ticked row is checked.
    const box = within(card).getByLabelText(
      "Meta Standard",
    ) as HTMLInputElement;
    await within(card).findByTestId("model-id-meta/muse-spark-1.3-contributor");
    expect(box.checked).toBe(true);
    expect(
      within(card).getByTestId("provider-enabled-meta").textContent,
    ).toBe("Meta connected · meta/muse-spark-1.3-contributor");
    expect(card.textContent).not.toContain("None enabled");
  });

  it("not-known rows fold behind Show all until opened", async () => {
    stubServed({
      providers: [{ provider_id: "openai" }],
      models: {
        openai: {
          provider_id: "openai",
          source: "provider",
          enabled: ["openai/gpt-4o-mini"],
          models: [
            {
              model: "gpt-4o-mini",
              enabled: true,
              in_base: true,
              kb: null,
            },
          ],
        },
      },
    });
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    const card = cardFor("openai");
    expect(
      within(card).getByTestId("provider-enabled-openai").textContent,
    ).toBe("OpenAI connected · openai/gpt-4o-mini");
    // Catalog-only gpt-4o has no price and no tick: folded, still in DOM.
    const full = within(card).getByTestId("model-id-openai/gpt-4o");
    const row = full.closest("li");
    expect(row?.getAttribute("hidden")).not.toBeNull();
    const toggle = within(card).getByTestId("provider-models-toggle-openai");
    expect(toggle.textContent).toContain("Show all");
    fireEvent.click(toggle);
    expect(row?.getAttribute("hidden")).toBeNull();
    expect(toggle.textContent).toContain("Show fewer");
    // The served-enabled row stayed visible throughout.
    expect(
      within(card)
        .getByTestId("model-id-openai/gpt-4o-mini")
        .closest("li")
        ?.getAttribute("hidden"),
    ).toBeNull();
  });
});
