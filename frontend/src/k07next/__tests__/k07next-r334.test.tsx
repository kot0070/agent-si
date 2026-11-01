/** @vitest-environment jsdom */
// K07NEXT R-334: the REAL LocaleSwitch over a fresh HttpApiClient
// (only global fetch replaced, quoting the served locale-switch
// schema from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import {
  LOCALE_STORAGE_KEY,
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { LocaleSwitch } from "../LocaleSwitch";

const SERVED_SWITCH = {
  row: "R-334",
  locales: ["en", "uk"],
  visible_switch: { top_bar: true, settings: true },
  persisted_via: "agentsi.locale",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  vi.stubGlobal("fetch", async (input: unknown) => {
    if (String(input) === "/api/v1/k07next/locale-switch") {
      return jsonBody(SERVED_SWITCH);
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next R-334 locale switch over the real screen", () => {
  it("shows the served locales and persists the chosen one", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocaleSwitch />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-locale-switch");
    expect(screen.getByText(en.shell.topbar.language)).toBeTruthy();
    expect(
      screen.getByTestId("k07next-locale-options").textContent,
    ).toBe("en,uk");
    expect(screen.getByTestId("k07next-locale-persist").textContent).toBe(
      "agentsi.locale",
    );
    fireEvent.click(screen.getByText("Українська"));
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("uk");
    expect(screen.getByText(uk.shell.topbar.language)).toBeTruthy();
  });
});
