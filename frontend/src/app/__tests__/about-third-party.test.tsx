/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import packageJson from "../../../package.json";
import { About, LICENCE_LINE } from "../About";
import { THIRD_PARTY_NOTICES } from "../thirdPartyNotices";

const RUNTIME_DEPS: Record<string, string> = packageJson.dependencies as Record<
  string,
  string
>;

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe.each(["en", "uk"] as const)("R-372 About in %s", (locale) => {
  it("shows the licence line plus third-party notices", async () => {
    setLocale(locale);
    render(<About showThirdParty />);
    expect(LICENCE_LINE).toBe("Copyright (c) 2026 Ivan Soprun");
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    expect(screen.getByTestId("about-third-party")).toBeTruthy();
    expect(screen.getByText(t("about.thirdParty.title"))).toBeTruthy();
    expect(THIRD_PARTY_NOTICES.length).toBeGreaterThanOrEqual(3);
    for (const notice of THIRD_PARTY_NOTICES) {
      const row = await screen.findByTestId(`third-party-${notice.name}`);
      expect(row.textContent).toContain(notice.name);
      expect(row.textContent).toContain(notice.version);
      expect(row.textContent).toContain(notice.licence);
      expect(notice.version).toBe(
        RUNTIME_DEPS[notice.name].replace(/^[~^]/, ""),
      );
    }
  });

  it("lists every runtime dependency, so a new dep fails until noticed", () => {
    const listed = new Set(THIRD_PARTY_NOTICES.map((notice) => notice.name));
    for (const name of Object.keys(RUNTIME_DEPS)) {
      expect(listed.has(name), `${name} needs a third-party notice`).toBe(
        true,
      );
    }
  });
});
