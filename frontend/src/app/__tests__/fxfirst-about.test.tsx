/** @vitest-environment jsdom */
// FXFIRST item 6: the licence reads preformatted and the third-party rows
// are a table with spaced cells, in both locales. No fetch anywhere.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { About, AGENT_SI_NAME, LICENCE_LINE } from "../About";
import { THIRD_PARTY_NOTICES } from "../thirdPartyNotices";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  vi.stubGlobal("fetch", async () => {
    throw new Error("About must not fetch");
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe.each(["en", "uk"] as const)("fxfirst About in %s", (locale) => {
  it("preformats the licence and tables the third-party notices", () => {
    render(<About locale={locale} showThirdParty />);
    expect(screen.getByText(AGENT_SI_NAME)).toBeTruthy();
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    const licence = screen.getByTestId("about-licence-text");
    expect(licence.tagName).toBe("PRE");
    expect(licence.textContent).toContain("Copyright (c) 2026 Ivan Soprun");
    if (locale === "en") {
      expect(licence.textContent).toContain("MIT License");
      expect(licence.textContent).toContain("Permission is hereby granted");
    } else {
      expect(licence.textContent).toContain("Ліцензія MIT");
    }
    const table = screen.getByTestId("about-third-party").querySelector("table");
    expect(table).not.toBeNull();
    for (const notice of THIRD_PARTY_NOTICES) {
      const row = screen.getByTestId(`third-party-${notice.name}`);
      expect(row.tagName).toBe("TR");
      const cells = within(row).getAllByRole("cell");
      expect(cells.map((cell) => cell.textContent)).toEqual([
        notice.name,
        notice.version,
        notice.licence,
      ]);
    }
  });
});

describe("fxfirst About licence keeps the full text", () => {
  it("contains the permission grant verbatim", () => {
    const view = render(<About locale="en" />);
    expect(view.container.textContent).toContain(en.about.licence.mitText);
  });
});
