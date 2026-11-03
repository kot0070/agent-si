/**
 * @vitest-environment jsdom
 */
// FXSMALL item 3 (W18): a project with no run yet reads "No checks yet" /
// "No action yet" on /watcher (and the rail card shares describeLastAction
// plus the noChecksYet key), never the "not known" placeholder. en + uk.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { WatcherTab, describeLastAction } from "./WatcherTab";
import { resetLocaleForTests, setLocale } from "../locale/index";

const EMPTY_STATUS = {
  project_id: "proj-empty",
  integrity_ok: true,
  journal_head: "evt-0000",
  generated_at: "2026-10-27T00:00:00Z",
};

const EMPTY_JOURNAL: unknown[] = [];

function stubEmpty(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: unknown) => {
      const text = String(url);
      return {
        ok: true,
        status: 200,
        json: async () => (text.includes("/api/v1/watcher/journal") ? EMPTY_JOURNAL : EMPTY_STATUS),
      };
    }),
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
});

describe("fxsmall3 watcher empty-state words", () => {
  it("en: no run yet reads No checks yet / No action yet", async () => {
    setLocale("en");
    stubEmpty();
    render(<WatcherTab projectId="proj-empty" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(screen.getByTestId("watcher-last-check").textContent).toBe(
      "Last check: No checks yet",
    );
    expect(screen.getByTestId("watcher-last-action").textContent).toBe(
      "Last action: No action yet",
    );
    expect(describeLastAction(undefined)).toBe("No action yet");
  });

  it("uk: no run yet reads the uk sentences", async () => {
    setLocale("uk");
    stubEmpty();
    render(<WatcherTab projectId="proj-empty" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(screen.getByTestId("watcher-last-check").textContent).toBe(
      "Остання перевірка: Перевірок ще немає",
    );
    expect(screen.getByTestId("watcher-last-action").textContent).toBe(
      "Остання дія: Дій ще немає",
    );
    expect(describeLastAction(undefined)).toBe("Дій ще немає");
  });
});
