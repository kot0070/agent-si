/**
 * @vitest-environment jsdom
 */
// FXFIRSTRUN L1/L2/L3 + Row F08: the Connect dialog is a real centred
// modal (backdrop, initial focus in the key field, Esc/backdrop close);
// the "Connected {label}." line appears ONLY after a
// real route round-trip (never on an empty/unreachable store); model
// rows name the real model id and explain the disabled checkbox.
// Network is the only fake (global fetch); no component doubles.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ProvidersPage } from "./ProvidersPage";
import { createMemorySecretStore } from "./secretStore";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { clearUiToken, setUiToken } from "../../api/errors";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubRoutes(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown) => {
      const url = String(input);
      if (url === "/api/v1/providers") {
        return json({ providers: [] });
      }
      if (url === "/api/v1/providers/keys") {
        return json(
          {
            key_ref: { secret_id: "meta", provider_id: "meta" },
          },
          201,
        );
      }
      if (url === "/api/v1/providers/connect") {
        return json({ provider: { provider_id: "meta" } });
      }
      return json({});
    },
  );
}

function stubUnreachable(): void {
  vi.stubGlobal("fetch", async () => {
    throw new Error("network unreachable");
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  setUiToken("fxmodal-session");
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

function openMetaDialog(): HTMLElement {
  fireEvent.click(screen.getByLabelText("Connect Meta"));
  return screen.getByRole("dialog");
}

describe("F08 connect opens a real centred modal", () => {
  it("dialog sits inside a backdrop, focuses the key field, Esc closes", async () => {
    stubRoutes();
    render(<ProvidersPage project_id="local" />);
    const dialog = openMetaDialog();
    expect(dialog.getAttribute("aria-label")).toBe("Connect Meta");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    // The modal is a centred overlay: a backdrop wraps the dialog.
    const backdrop = screen.getByTestId("connect-backdrop");
    expect(backdrop.contains(dialog)).toBe(true);
    // Initial focus lands in the key field, not on a button.
    const keyField = within(dialog).getByLabelText("API key");
    expect(document.activeElement).toBe(keyField);
    // Save is the single primary action; X and Cancel stay quiet.
    const save = within(dialog).getByText("Save");
    expect(save.getAttribute("data-variant")).toBe("primary");
    expect(within(dialog).getByText("Cancel").getAttribute("data-variant")).toBe(
      "quiet",
    );
    // Esc closes the modal.
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Cancel, X and backdrop clicks close the modal", () => {
    stubRoutes();
    render(<ProvidersPage project_id="local" />);
    openMetaDialog();
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByRole("dialog")).toBeNull();

    openMetaDialog();
    fireEvent.click(screen.getByLabelText("Close"));
    expect(screen.queryByRole("dialog")).toBeNull();

    openMetaDialog();
    fireEvent.click(screen.getByTestId("connect-backdrop"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("disconnect opens the same kind of centred modal", async () => {
    stubRoutes();
    render(<ProvidersPage project_id="local" />);
    const dialog = openMetaDialog();
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "sk-test" },
    });
    // FXR2E two-step (416ddaa, merged 0661228): Check before Save.
    fireEvent.click(within(dialog).getByText("Check"));
    expect(await within(dialog).findByText("Key checked. Save to connect.")).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Save"));
    expect(await screen.findByLabelText("Disconnect Meta")).toBeTruthy();
    // Step 2 stays open: Done closes it before opening the disconnect modal.
    fireEvent.click(within(screen.getByRole("dialog")).getByText("Done"));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByLabelText("Disconnect Meta"));
    const disc = screen.getByRole("dialog");
    expect(disc.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByTestId("disconnect-backdrop").contains(disc)).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("L2 success only after a real save", () => {
  it("empty key keeps Save disabled: nothing to report", () => {
    stubRoutes();
    render(<ProvidersPage project_id="local" />);
    const dialog = openMetaDialog();
    expect(
      (within(dialog).getByText("Save") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.queryByText("Connected Meta.")).toBeNull();
  });

  it("unreachable routes never show Connected: honest error, card stays put", async () => {
    stubUnreachable();
    render(<ProvidersPage project_id="local" />);
    const dialog = openMetaDialog();
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "sk-test" },
    });
    // FXR2E two-step: the unreachable store fails at Check (Save never
    // enables), with the same honest error and nothing stored.
    fireEvent.click(within(dialog).getByText("Check"));
    // S3: slow/unreachable keeps the key; the page names Connect again,
    // never the re-paste hint.
    expect(await within(dialog).findByText("The provider is slow or unreachable. Your key is saved. Press Connect again.")).toBeTruthy();
    expect(screen.queryByText(/Reference saved/)).toBeNull();
    // Nothing was saved: the Meta card still offers Connect, never
    // Disconnect (the open dialog shares the accessible name, so the
    // card is addressed through its own test id).
    expect(screen.queryByLabelText("Disconnect Meta")).toBeNull();
    const metaCard = screen
      .getAllByTestId("provider-card")
      .find((card) => card.getAttribute("data-provider-id") === "meta");
    expect(metaCard).toBeTruthy();
    expect(
      within(metaCard as HTMLElement).getByLabelText("Connect Meta"),
    ).toBeTruthy();
  });

  it("real route round-trip on an empty store shows Connected once", async () => {
    stubRoutes();
    render(<ProvidersPage project_id="local" />);
    const before = await createMemorySecretStore("fxmodal-session").list(
      "agent_si/provider/",
    );
    expect(before).toHaveLength(0);
    const dialog = openMetaDialog();
    fireEvent.change(within(dialog).getByLabelText("API key"), {
      target: { value: "sk-test" },
    });
    // FXR2E two-step (416ddaa, merged 0661228): Check before Save.
    fireEvent.click(within(dialog).getByText("Check"));
    expect(
      await within(dialog).findByText("Key checked. Save to connect."),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Save"));
    // Step 2 in the same dialog: Connected line plus the tickable list.
    // Done closes it; the card keeps the quiet Connected line.
    expect(
      await within(dialog).findByText("Connected Meta."),
    ).toBeTruthy();
    expect(await screen.findByLabelText("Disconnect Meta")).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("Connected Meta.")).toBeTruthy();
  });
});

describe("L3 model rows name the real model id", () => {
  it("each row shows the model id and explains the disabled checkbox", () => {
    stubRoutes();
    render(<ProvidersPage project_id="local" />);
    const metaId = screen.getByText("meta/muse-spark-1.3-contributor");
    expect(metaId.tagName.toLowerCase()).toBe("small");
    const box = screen.getByLabelText(
      "Meta Standard",
    ) as HTMLInputElement;
    expect(box.disabled).toBe(true);
    expect(box.title.length).toBeGreaterThan(0);
  });
});
