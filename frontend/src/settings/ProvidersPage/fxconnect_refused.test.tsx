/**
 * @vitest-environment jsdom
 *
 * FXR2E wrong key: a refused save shows the plain refused text (never a
 * machine code) and the card stays Connect; an unreachable provider
 * shows the unreachable text. The key never reaches any store, so no
 * Connected line appears. Network is the only fake (global fetch).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";

const FX_TOKEN = "fxrefused-token-01";
const REFUSED = "The provider refused this key. Paste the full key again.";
// S3: slow/unreachable keeps the key; the page names Connect again,
// never the re-paste hint.
const UNREACHABLE =
  "The provider is slow or unreachable. Your key is saved. Press Connect again.";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(handler: (url: string) => Response | Promise<Response>): void {
  vi.stubGlobal("fetch", async (input: unknown) => handler(String(input)));
}

function baseStub(url: string): Response {
  if (url === "/api/v1/providers") {
    return json({ providers: [] });
  }
  if (url === "/api/v1/local/models") {
    return json([]);
  }
  if (/^\/api\/v1\/providers\/[^/]+\/models$/.test(url)) {
    return json({ provider_id: "openai", models: [] });
  }
  if (url === "/api/v1/local/connect") {
    return json({ status: "NOT_CONFIGURED", reason: "attached" });
  }
  return json({});
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

async function saveWrongKey(): Promise<void> {
  render(<ProvidersPage project_id="local" />);
  fireEvent.click(screen.getByLabelText("Connect OpenAI"));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("API key"), {
    target: { value: "abc" },
  });
  // Two-step dialog: paste + Check first (read-only route, never
  // stores); a refused/unreachable key reports here and Save stays
  // disabled. Save is covered by the success path below.
  fireEvent.click(within(dialog).getByText("Check"));
}

describe("FXR2E refused key stays disconnected", () => {
  it("401 shows the refused text and the card stays Connect", async () => {
    stubFetch((url) => {
      if (url === "/api/v1/providers/keys/check") {
        return json(
          { code: "PROVIDER_KEY_REFUSED", message: REFUSED },
          401,
        );
      }
      if (url === "/api/v1/providers/keys") {
        return json(
          { code: "PROVIDER_KEY_REFUSED", message: REFUSED },
          401,
        );
      }
      return baseStub(url);
    });
    await saveWrongKey();
    expect(await screen.findByText(REFUSED)).toBeTruthy();
    expect(screen.queryByText(/Connected OpenAI/)).toBeNull();
  });

  it("503 shows the unreachable text and the card stays Connect", async () => {
    stubFetch((url) => {
      if (url === "/api/v1/providers/keys/check") {
        return json(
          { code: "EVIDENCE_PROBE_NETWORK", message: UNREACHABLE },
          503,
        );
      }
      if (url === "/api/v1/providers/keys") {
        return json(
          { code: "EVIDENCE_PROBE_NETWORK", message: UNREACHABLE },
          503,
        );
      }
      return baseStub(url);
    });
    await saveWrongKey();
    expect(await screen.findByText(UNREACHABLE)).toBeTruthy();
    expect(screen.queryByText(/Connected OpenAI/)).toBeNull();
  });

  it("no fallback code is shown for a coded refusal", async () => {
    stubFetch((url) => {
      if (url === "/api/v1/providers/keys/check") {
        return json(
          { code: "PROVIDER_KEY_REFUSED", message: REFUSED },
          401,
        );
      }
      if (url === "/api/v1/providers/keys") {
        return json(
          { code: "PROVIDER_KEY_REFUSED", message: REFUSED },
          401,
        );
      }
      return baseStub(url);
    });
    await saveWrongKey();
    await screen.findByText(REFUSED);
    await waitFor(() => {
      expect(document.body.textContent ?? "").not.toContain(
        "CONTEXT_WRONG_CONTRACT_VERSION",
      );
    });
  });

  it("Check then Save success stores and shows Connected", async () => {
    stubFetch((url) => {
      if (url === "/api/v1/providers/keys/check") {
        return json({ ok: true }, 200);
      }
      if (url === "/api/v1/providers/keys") {
        return json(
          { key_ref: { secret_id: "openai", provider_id: "openai" } },
          201,
        );
      }
      if (url === "/api/v1/providers/connect") {
        return json({ status: "connected" }, 200);
      }
      return baseStub(url);
    });
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "good-key" },
    });
    expect(
      (within(dialog).getByText("Save") as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.click(within(dialog).getByText("Check"));
    await screen.findByText("Key checked. Save to connect.");
    expect(
      (within(dialog).getByText("Save") as HTMLButtonElement).disabled,
    ).toBe(false);
    fireEvent.click(within(dialog).getByText("Save"));
    const connected = await screen.findAllByText(/Connected OpenAI/);
    expect(connected.length).toBeGreaterThan(0);
  });
});
