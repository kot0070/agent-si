/** @vitest-environment jsdom */
// K07NEXT M-P4-139: the REAL CopyrightLine over a fresh HttpApiClient
// (only global fetch replaced, quoting the served copyright schema
// from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { CopyrightLine } from "../CopyrightLine";

const COPYRIGHT = "Copyright (c) 2026 Ivan Soprun";

const SERVED_COPYRIGHT = {
  row: "M-P4-139",
  line_en: COPYRIGHT,
  line_uk: COPYRIGHT,
  shown_in: ["About", "installer-metadata"],
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  vi.stubGlobal("fetch", async (input: unknown) => {
    if (String(input) === "/api/v1/k07next/copyright") {
      return jsonBody(SERVED_COPYRIGHT);
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

describe("k07next M-P4-139 copyright line over the real screen", () => {
  it("shows the exact copyright line in English and Ukrainian", async () => {
    setLocale("en");
    const english = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <CopyrightLine />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-copyright");
    expect(screen.getByTestId("k07next-copyright-en").textContent).toBe(
      COPYRIGHT,
    );
    expect(screen.getByTestId("k07next-copyright-uk").textContent).toBe(
      COPYRIGHT,
    );
    expect(t("about.licence.line")).toBe(en.about.licence.line);
    english.unmount();
    cleanup();
    setLocale("uk");
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <CopyrightLine />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-copyright");
    expect(t("about.licence.line")).toBe(uk.about.licence.line);
    expect(screen.getByTestId("k07next-copyright-en").textContent).toBe(
      uk.about.licence.line,
    );
  });
});
