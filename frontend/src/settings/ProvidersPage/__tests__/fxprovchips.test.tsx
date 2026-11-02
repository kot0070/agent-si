/**
 * @vitest-environment jsdom
 *
 * FXPROVCHIPS: model rows render TWO quiet chips (capability state + base
 * state), never the glued sentence "not known not in capability base".
 * Network is the only fake (global fetch); no component doubles.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../../api/errors";
import { resetLocaleForTests, setLocale } from "../../../locale/index";
import { ProvidersPage } from "../ProvidersPage";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubServed(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/providers") {
      return json({ providers: [] });
    }
    if (url === "/api/v1/local/models") {
      return json([]);
    }
    const match = url.match(/^\/api\/v1\/providers\/([^/]+)\/models$/);
    if (match !== null) {
      return json({
        provider_id: "openai",
        source: "provider",
        enabled: ["openai/gpt-4o-mini"],
        models: [
          { id: "openai/gpt-4o-mini", name: "Mini", price: 0.15, kb_known: true },
          { id: "openai/gpt-4o", name: "Full", price: null, kb: null, kb_known: false },
        ],
      });
    }
    if (url === "/api/v1/providers/keys") {
      return json({ key_ref: { secret_id: "fx", provider_id: "fx" } }, 201);
    }
    if (url === "/api/v1/providers/connect") {
      return json({ provider: { provider_id: "fx" } });
    }
    return json({});
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  setUiToken("fxprovchips-token");
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

describe("FXPROVCHIPS two quiet chips, no glued sentence", () => {
  it("unknown-price + outside-base row shows two quiet chips, not one glued line", async () => {
    stubServed();
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "sk-fxprovchips" },
    });
    fireEvent.click(within(dialog).getByText("Save"));
    const rows = await within(dialog).findAllByTestId("connect-model-row");
    expect(rows).toHaveLength(2);
    const fullRow = rows[1];
    // No glued sentence anywhere in the row.
    expect(fullRow.textContent ?? "").not.toContain("not known not in capability base");
    // Two separate quiet chips: base (price) state + capability state.
    const priceChip = within(fullRow).getByTestId("connect-model-price-openai/gpt-4o");
    const kbChip = within(fullRow).getByTestId("connect-model-kb-openai/gpt-4o");
    expect(priceChip.getAttribute("data-variant")).toBe("quiet");
    expect(kbChip.getAttribute("data-variant")).toBe("quiet");
    expect(priceChip.textContent).toBe("not known");
    expect(kbChip.textContent ?? "").toContain("not in capability base");
    expect(priceChip).not.toBe(kbChip);
    // Known row also carries two quiet chips.
    const miniRow = rows[0];
    const miniPrice = within(miniRow).getByTestId("connect-model-price-openai/gpt-4o-mini");
    const miniKb = within(miniRow).getByTestId("connect-model-kb-openai/gpt-4o-mini");
    expect(miniPrice.getAttribute("data-variant")).toBe("quiet");
    expect(miniKb.getAttribute("data-variant")).toBe("quiet");
    expect(miniPrice.textContent).toBe("$0.15");
    expect(miniKb.textContent ?? "").toContain("in capability base");
  });
});
