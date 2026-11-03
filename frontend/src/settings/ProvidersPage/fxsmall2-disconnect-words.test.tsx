/**
 * @vitest-environment jsdom
 */
// FXSMALL item 2: a refused/failed disconnect reads as a plain sentence;
// the machine code stays behind the Details disclosure, never in the alert.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DisconnectDialog } from "./DisconnectDialog";
import { createMemorySecretStore, secretIdForProvider } from "./secretStore";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";

function stubDisconnect404(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 404,
      json: async () => ({ code: "CONTEXT_MISSING" }),
    })),
  );
}

function renderOpenDialog() {
  const store = createMemorySecretStore("t");
  const secretId = secretIdForProvider("openai");
  return { store, secretId };
}

beforeEach(() => {
  setUiToken("t");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

describe("fxsmall2 disconnect failure words", () => {
  it("en: alert is a plain sentence, code lives in Details only", async () => {
    setLocale("en");
    stubDisconnect404();
    const { store, secretId } = renderOpenDialog();
    await store.save({
      secret_id: secretId,
      provider_id: "openai",
      type: "api-key",
      scope: "providers",
      source: "test",
      created_at: "2026-01-01T00:00:00.000Z",
      last_rotated_at: null,
    });
    render(
      <DisconnectDialog
        provider_id="openai"
        providerLabel="OpenAI"
        secretId={secretId}
        open
        store={store}
        sessionToken="t"
        onClose={() => {}}
        onDisconnected={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("Disconnect"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Disconnect failed.");
    expect(alert.textContent).not.toContain("CONTEXT_MISSING");
    const details = screen.getByText("Details").closest("details");
    expect(details?.textContent).toContain("CONTEXT_MISSING");
    expect(details?.textContent).toContain("404");
    // The dialog stays open: nothing was disconnected.
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("uk: alert is a plain sentence, code lives in Details only", async () => {
    setLocale("uk");
    stubDisconnect404();
    const { store, secretId } = renderOpenDialog();
    await store.save({
      secret_id: secretId,
      provider_id: "openai",
      type: "api-key",
      scope: "providers",
      source: "test",
      created_at: "2026-01-01T00:00:00.000Z",
      last_rotated_at: null,
    });
    render(
      <DisconnectDialog
        provider_id="openai"
        providerLabel="OpenAI"
        secretId={secretId}
        open
        store={store}
        sessionToken="t"
        onClose={() => {}}
        onDisconnected={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("Від'єднати"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Не вдалося від'єднати.");
    expect(alert.textContent).not.toContain("CONTEXT_MISSING");
    const details = screen.getByText("Деталі").closest("details");
    expect(details?.textContent).toContain("CONTEXT_MISSING");
    expect(await screen.findByRole("dialog")).toBeTruthy();
  });
});
