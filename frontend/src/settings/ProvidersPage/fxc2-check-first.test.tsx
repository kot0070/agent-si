/** @vitest-environment jsdom */
// FXC2 kept focused test: a disabled Save names its reason on screen.
// The `connect-check-first` line shows only while Save is disabled for
// the unchecked-key reason (cloud preset, key present, not checked) and
// disappears once Check succeeds.
import { describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { getPreset, PROVIDER_CATALOG } from "./catalog";
import { ConnectDialog } from "./ConnectDialog";
import { createMemorySecretStore } from "./secretStore";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { clearUiToken, setUiToken } from "../../api/errors";

function openaiPreset() {
  const preset = getPreset(PROVIDER_CATALOG, "openai");
  if (!preset) {
    throw new Error("openai preset missing");
  }
  return preset;
}

describe("fxc2 check-first hint", () => {
  it("appears with a key before check, disappears after check", async () => {
    resetLocaleForTests();
    setLocale("en");
    setUiToken("local-session");
    vi.stubGlobal("fetch", async (input: unknown) => {
      const url = String(input);
      const body = (data: unknown, status = 200): Response =>
        new Response(JSON.stringify(data), {
          status,
          headers: { "content-type": "application/json" },
        });
      if (url === "/api/v1/providers/keys/check") return body({ ok: true }, 200);
      return body({});
    });
    try {
      const store = createMemorySecretStore("sess-fxc2-hint");
      render(
        <ConnectDialog
          preset_id="openai"
          preset={openaiPreset()}
          open
          store={store}
          onClose={() => {}}
          onConnected={() => {}}
        />,
      );
      expect(screen.queryByTestId("connect-check-first")).toBeNull();
      fireEvent.change(screen.getByLabelText("API key"), {
        target: { value: "sk-test" },
      });
      expect(await screen.findByTestId("connect-check-first")).toBeTruthy();
      expect(
        screen.getByTestId("connect-check-first").textContent,
      ).toBe("Check the key first.");
      fireEvent.click(screen.getByText("Check"));
      await screen.findByText("Key checked. Save to connect.");
      expect(screen.queryByTestId("connect-check-first")).toBeNull();
    } finally {
      cleanup();
      vi.unstubAllGlobals();
      resetLocaleForTests();
      clearUiToken();
    }
  });
});
