/**
 * @vitest-environment jsdom
 */
// FXSMALL item 6 (dialog half): a conflicting re-connect answers 400 with
// PROVIDER_CONFLICT; the dialog shows one plain sentence (en + uk) and
// never says Connected.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";

const FX_TOKEN = "fx-ui-token-01";
const FX_KEY = "fixture-connect-value";

function programFetch(handler: (url: string) => unknown) {
  const seen: string[] = [];
  const mock = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    seen.push(`${(init?.method ?? "GET").toUpperCase()} ${url}`);
    return handler(url);
  });
  vi.stubGlobal("fetch", mock);
  return seen;
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function httpError(status: number, body: unknown) {
  return { ok: false, status, json: async () => body };
}

beforeEach(() => {
  setLocale("en");
  setUiToken(FX_TOKEN);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

function stubConflict() {
  return programFetch((url) => {
    if (url === "/api/v1/providers") {
      return ok({ providers: [] });
    }
    if (url === "/api/v1/providers/keys/check") {
      return ok({ ok: true });
    }
    if (url === "/api/v1/providers/keys") {
      return { ok: true, status: 201, json: async () => ({}) };
    }
    if (url === "/api/v1/providers/connect") {
      return httpError(400, {
        code: "PROVIDER_CONFLICT",
        message: "provider 'openai' is already connected with a different base URL",
      });
    }
    return ok({});
  });
}

async function runConflictFlow(connectLabel: string): Promise<void> {
  render(<ProvidersPage project_id="local" />);
  fireEvent.click(await screen.findByLabelText(connectLabel));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText(/API key|Ключ API/), {
    target: { value: FX_KEY },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: /^(Check|Перевірити)$/ }));
  await within(dialog).findByText(/Key checked|Ключ перевірено/);
  fireEvent.click(within(dialog).getByRole("button", { name: /^(Save|Зберегти)$/ }));
}

describe("fxsmall6 conflicting re-connect dialog", () => {
  it("en: one plain sentence, never Connected", async () => {
    setLocale("en");
    stubConflict();
    await runConflictFlow("Connect OpenAI");
    const dialog = screen.getByRole("dialog");
    expect(
      await within(dialog).findByText(/already connected with different settings/),
    ).toBeTruthy();
    expect(screen.queryByText("Connected OpenAI.")).toBeNull();
    expect(dialog.textContent).not.toContain("PROVIDER_CONFLICT");
    expect(dialog.textContent).not.toContain("Connected OpenAI.");
  });

  it("uk: one plain sentence, never Connected", async () => {
    setLocale("uk");
    stubConflict();
    await runConflictFlow("Під'єднати OpenAI");
    const dialog = screen.getByRole("dialog");
    expect(
      await within(dialog).findByText(/вже під'єднано з іншими налаштуваннями/),
    ).toBeTruthy();
    expect(screen.queryByText("Під’єднано OpenAI.")).toBeNull();
    expect(dialog.textContent).not.toContain("PROVIDER_CONFLICT");
  });
});
