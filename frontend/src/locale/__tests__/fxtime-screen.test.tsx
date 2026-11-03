/** @vitest-environment jsdom */
// FXTIME helper proof: one 24-hour form in en + uk. Today reads HH:mm;
// older stamps read "d MMM HH:mm" with the locale month name (uk months in
// uk); invalid input falls back to the raw value, never an invented time.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup } from "@testing-library/react";
import {
  formatScreenTime,
  resetLocaleForTests,
  setLocale,
} from "../index";

const OLD = "2026-02-11T19:25:00Z";

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("fxtime formatScreenTime", () => {
  it("renders today as zero-padded 24-hour HH:mm in both locales", () => {
    const at = Date.now();
    for (const locale of ["en", "uk"] as const) {
      const text = formatScreenTime(at, locale);
      expect(text).toMatch(/^\d\d:\d\d$/);
      const stamp = new Date(at);
      const pad = (n: number): string => String(n).padStart(2, "0");
      expect(text).toBe(`${pad(stamp.getHours())}:${pad(stamp.getMinutes())}`);
    }
  });

  it("renders an older stamp as d MMM HH:mm in en", () => {
    setLocale("en");
    const text = formatScreenTime(OLD, "en");
    const stamp = new Date(OLD);
    const pad = (n: number): string => String(n).padStart(2, "0");
    expect(text).toBe(
      `${stamp.getDate()} Feb ${pad(stamp.getHours())}:${pad(stamp.getMinutes())}`,
    );
    expect(text).not.toMatch(/AM|PM/);
  });

  it("renders the same older stamp with a uk month name in uk", () => {
    const en = formatScreenTime(OLD, "en");
    const uk = formatScreenTime(OLD, "uk");
    expect(uk).not.toBe(en);
    expect(uk).toMatch(/[\u0400-\u04FF]/);
    expect(uk).not.toMatch(/AM|PM/);
    expect(uk).toMatch(/^\d{1,2} \S+ \d\d:\d\d$/);
  });

  it("keeps 24-hour time for evening hours, never 12-hour", () => {
    const evening = new Date(2026, 1, 11, 19, 25, 0).getTime();
    const text = formatScreenTime(evening, "en");
    expect(text).toContain("19:25");
    expect(text).not.toContain("07:25");
    expect(text).not.toMatch(/AM|PM/i);
  });

  it("falls back to the raw value for invalid input", () => {
    expect(formatScreenTime("not-a-date", "en")).toBe("not-a-date");
    expect(formatScreenTime("", "uk")).toBe("");
  });

  it("accepts Date and epoch inputs", () => {
    const stamp = new Date(OLD);
    expect(formatScreenTime(stamp, "en")).toBe(formatScreenTime(OLD, "en"));
    expect(formatScreenTime(stamp.getTime(), "en")).toBe(
      formatScreenTime(OLD, "en"),
    );
  });
});
