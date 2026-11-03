/**
 * @vitest-environment jsdom
 *
 * FXUK L7: the uk models page must not render hard-coded English catalog
 * strings (keyHint, group, model labels) nor other English UI literals;
 * the en page keeps English. Uses the REAL ProvidersPage through the
 * connect flow (Manage models + connected-model line only render when
 * connected). Network is the only fake.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ProvidersPage } from "./ProvidersPage";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { clearUiToken, setUiToken } from "../../api/errors";

function stubAll(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown) => {
      const url = String(input);
      const body = (data: unknown, status = 200): Response =>
        new Response(JSON.stringify(data), {
          status,
          headers: { "content-type": "application/json" },
        });
      if (url === "/api/v1/providers") {
        return body({ providers: [] });
      }
      if (url === "/api/v1/providers/keys/check") {
        return body({ ok: true }, 200);
      }
      if (url === "/api/v1/providers/keys") {
        return body({ key_ref: { secret_id: "openai", provider_id: "openai" } }, 201);
      }
      if (url === "/api/v1/providers/connect") {
        return body({ provider: { provider_id: "openai" } });
      }
      return body({});
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setUiToken("fxuk-l7");
  stubAll();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

// Full connect flow through the real dialog; labels differ per locale,
// Done is matched in both languages so the test survives the fix.
async function connectOpenai(connectLabel: string, checkLabel: string, apiKeyLabel: string, saveLabel: string): Promise<void> {
  fireEvent.click(screen.getByLabelText(connectLabel));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText(apiKeyLabel), { target: { value: "sk-test" } });
  fireEvent.click(within(dialog).getByText(checkLabel));
  await within(dialog).findByText(/Key checked|Ключ перевірено/);
  fireEvent.click(within(dialog).getByText(saveLabel));
  await within(dialog).findByText(/Connected OpenAI|Під’єднано OpenAI/);
  fireEvent.click(within(dialog).getByText(/Done|Готово/));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
}

const EN_HINTS = [
  "Key from your Meta dashboard.",
  "Any OpenAI-style key or token for your server.",
  "Local server: usually no key is needed.",
  "Key from AI Studio",
  "Key from the Mistral console.",
  "Key from the xAI console.",
];

describe("fxuk-l7 models page locale", () => {
  it("uk: no English keyHints, groups, model labels, Manage text or enabled", async () => {
    setLocale("uk");
    const { container } = render(<ProvidersPage project_id="local" />);
    await connectOpenai("Під'єднати OpenAI", "Перевірити", "Ключ API", "Зберегти");
    const text = container.textContent ?? "";
    for (const hint of EN_HINTS) {
      expect(text).not.toContain(hint);
    }
    expect(text).not.toContain('Starts with "');
    expect(text).not.toContain("Standard");
    expect(text).not.toContain("Advanced");
    expect(text).not.toContain("Manage models");
    expect(text).not.toContain("enabled");
    expect(text).not.toContain("not known");
    expect(screen.queryByRole("heading", { name: "Cloud" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Local" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Compatible" })).toBeNull();
    // Localized content renders; product names stay.
    // FXLOOK D4: the connected line reads "підключено · model".
    expect(text).toContain("Постачальники");
    expect(text).toContain("Керувати моделями");
    expect(text).toContain("підключено");
    expect(text).toContain("невідомо");
    expect(text).toContain("Meta");
  });

  it("en: keeps the English catalog strings", async () => {
    setLocale("en");
    const { container } = render(<ProvidersPage project_id="local" />);
    await connectOpenai("Connect OpenAI", "Check", "API key", "Save");
    const text = container.textContent ?? "";
    expect(text).toContain("Key from your Meta dashboard.");
    expect(text).toContain("Manage models");
    // FXLOOK D4: the connected line names connection + model, not a count.
    expect(text).toContain("OpenAI connected · openai/gpt-4o-mini");
    expect(screen.getByRole("heading", { name: "Cloud" })).toBeTruthy();
  });
});
