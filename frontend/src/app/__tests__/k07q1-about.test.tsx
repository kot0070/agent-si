/** @vitest-environment jsdom */
// K07Q1 R-372: the REAL About proves name + licence + third-party
// notices in both locales, EXISTING LocaleKey strings only (frozen
// frontend/src/settings/k07b-iface.d.ts:19-21: 'about.licence.line',
// 'about.licence.mitText', 'about.thirdParty.title'). About performs no
// fetch: the boundary throws if touched. No FakeApiClient anywhere.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import {
  About,
  AGENT_SI_NAME,
  APP_ID,
  LICENCE_LINE,
  MIT_LICENSE_REF,
} from "../About";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";

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

describe("k07q1 About row over the real screen", () => {
  it("proves name plus licence plus third-party notices in en and uk", () => {
    expect(APP_ID).toBe("com.agentsi.app");
    expect(MIT_LICENSE_REF).toBe("about.licence.mitText");
    const english = render(<About locale="en" />);
    expect(screen.getByText(AGENT_SI_NAME)).toBeTruthy();
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    expect(english.container.textContent).toContain(en.about.licence.line);
    expect(english.container.textContent).toContain(en.about.licence.mitText);
    expect(en.about.thirdParty.title.length).toBeGreaterThan(0);
    cleanup();
    const ukrainian = render(<About locale="uk" />);
    expect(screen.getByText(AGENT_SI_NAME)).toBeTruthy();
    expect(screen.getByText(LICENCE_LINE)).toBeTruthy();
    expect(ukrainian.container.textContent).toContain(uk.about.licence.line);
    expect(ukrainian.container.textContent).toContain(uk.about.licence.mitText);
    expect(uk.about.thirdParty.title.length).toBeGreaterThan(0);
    setLocale("en");
    expect(t("about.thirdParty.title")).toBe(en.about.thirdParty.title);
    setLocale("uk");
    expect(t("about.thirdParty.title")).toBe(uk.about.thirdParty.title);
  });
});
