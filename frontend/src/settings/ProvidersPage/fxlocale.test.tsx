/**
 * @vitest-environment jsdom
 *
 * FXLOCALE1 durable test: the REAL ProvidersPage renders Ukrainian labels
 * and result messages under the uk locale and English under en.
 * No injected data: the page builds its own store and catalog entries.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ProvidersPage } from "./ProvidersPage";
import { resetLocaleForTests, setLocale } from "../../locale/index";

function stubProvidersApi(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown) => {
      const url = String(input);
      if (url === "/api/v1/providers") {
        return { ok: true, status: 200, json: async () => ({ providers: [] }) };
      }
      if (url === "/api/v1/providers/keys") {
        return {
          ok: true,
          status: 201,
          json: async () => ({ key_ref: { secret_id: "openai", provider_id: "openai" } }),
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

async function connectOpenaiThroughDialog(): Promise<void> {
  fireEvent.click(screen.getByLabelText("Connect OpenAI"));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("API key"), {
    target: { value: "sk-test" },
  });
  fireEvent.click(within(dialog).getByText("Save"));
  expect(await within(dialog).findByText("Connected OpenAI. Reference saved.")).toBeTruthy();
  fireEvent.click(within(dialog).getByText("Done"));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
}

describe("fxlocale provider connect screens", () => {
  it("renders English labels and result messages under en", async () => {
    setLocale("en");
    stubProvidersApi();
    render(<ProvidersPage project_id="local" />);
    expect(screen.getByText("Providers")).toBeTruthy();
    expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy();
    await connectOpenaiThroughDialog();
    expect(await screen.findByText("Connected OpenAI. Reference saved.")).toBeTruthy();
  });

  it("renders Ukrainian labels and result messages under uk", async () => {
    setLocale("uk");
    stubProvidersApi();
    render(<ProvidersPage project_id="local" />);
    expect(screen.getByText("Постачальники")).toBeTruthy();
    expect(screen.getByLabelText("Під'єднати OpenAI")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Під'єднати OpenAI"));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Ключ API"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(within(dialog).getByText("Зберегти"));
    // Step 2 in the same dialog carries the quiet line; the card shows it
    // too once Done closes the dialog.
    expect(await within(dialog).findByText("Під'єднано OpenAI. Посилання збережено.")).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(screen.getByLabelText("Від'єднати OpenAI")).toBeTruthy());
  });
});
