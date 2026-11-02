/** @vitest-environment jsdom */
// K07NEXT R-342: the REAL LicenceNotice over a fresh HttpApiClient
// (only global fetch replaced, quoting the served licence schema
// from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import en from "../../locale/en.json";
import { LicenceNotice } from "../LicenceNotice";

const LICENCE_LINE = "Copyright (c) 2026 Ivan Soprun";

const SERVED_LICENCE = {
  row: "R-342",
  licence_line: LICENCE_LINE,
  mit_ref: "about.licence.mitText",
  third_party_title_ref: "about.thirdParty.title",
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
    if (String(input) === "/api/v1/app/licence") {
      return jsonBody(SERVED_LICENCE);
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

describe("k07next R-342 licence notice over the real screen", () => {
  it("shows the exact served licence line everywhere user-visible", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LicenceNotice />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-licence");
    expect(
      screen.getByTestId("k07next-licence-line").textContent,
    ).toBe(LICENCE_LINE);
    expect(screen.getByTestId("k07next-licence-line").textContent).toBe(
      en.about.licence.line,
    );
    expect(t("about.licence.mitText")).toBe(en.about.licence.mitText);
    expect(screen.getAllByText(en.about.thirdParty.title)).toHaveLength(2);
  });
});
