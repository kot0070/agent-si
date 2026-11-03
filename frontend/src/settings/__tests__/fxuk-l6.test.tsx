/**
 * @vitest-environment jsdom
 *
 * FXUK L6 RED: maskLogDir masks the user-profile segment on every path
 * shape (win backslash + forward slash, /home/<n>, /Users/<n>) and keeps
 * the rest; the diagnostics page renders the masked path in en and uk.
 * Fails before the fix on posix profile fixtures.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DiagnosticsSection, maskLogDir } from "../DiagnosticsSection";
import { resetLocaleForTests, setLocale } from "../../locale/index";

function stubAbout(logsDir: string): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown) => {
      if (String(input) === "/api/v1/sidecar/about") {
        return { ok: true, status: 200, json: async () => ({ logs_dir: logsDir }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    },
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
});

describe("fxuk-l6 profile segment masking", () => {
  it("masks win profile, keeps the rest, leaves plain paths alone", () => {
    expect(maskLogDir("C:\\Users\\kot00\\AppData\\logs")).toBe("C:\\Users\\…\\AppData\\logs");
    expect(maskLogDir("D:\\agent\\data\\logs")).toBe("D:\\agent\\data\\logs");
  });

  it("masks posix and fwd-slash-win profile fixtures", () => {
    expect(maskLogDir("/home/kot00/.local/share/logs")).toBe("/home/…/.local/share/logs");
    expect(maskLogDir("/Users/kot00/Library/logs")).toBe("/Users/…/Library/logs");
    expect(maskLogDir("C:/Users/kot00/AppData/logs")).toBe("C:/Users/…/AppData/logs");
  });

  it.each(["en", "uk"] as const)("diagnostics renders masked profile path (%s)", async (locale) => {
    setLocale(locale);
    stubAbout("C:\\Users\\kot00\\AppData\\logs");
    render(
      <MemoryRouter>
        <DiagnosticsSection />
      </MemoryRouter>,
    );
    const line = await screen.findByTestId("diagnostics-log-files");
    expect(line.textContent).toContain("…");
    expect(line.textContent).not.toContain("kot00");
  });
});
