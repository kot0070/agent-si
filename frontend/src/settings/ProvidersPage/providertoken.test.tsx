// @vitest-environment jsdom
// The Models page must keep the window's session token: it once replaced it
// with a fixed value, so every later write in the window answered 403.
import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearUiToken, getUiToken, setUiToken } from "../../api/errors";
import { ProvidersPage } from "./ProvidersPage";

const WINDOW_TOKEN = "window-session-token";

beforeEach(() => {
  setUiToken(WINDOW_TOKEN);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })),
  );
});

afterEach(() => {
  clearUiToken();
  vi.unstubAllGlobals();
});

describe("ProvidersPage session token", () => {
  it("keeps the window token after mount", async () => {
    const view = render(<ProvidersPage project_id="p1" />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getUiToken()).toBe(WINDOW_TOKEN);
    view.unmount();
    expect(getUiToken()).toBe(WINDOW_TOKEN);
  });
});
