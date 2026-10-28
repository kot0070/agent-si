// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RULE_CARDS, RULE_CARD_MODELS } from "./ruleCards";
import {
  WATCHER_SETTINGS_KEY,
  cardModelKey,
} from "./watcherSettings";
import { WatcherTab } from "./WatcherTab";

// FAKE-OF: global fetch (fetch-level fake only)
function fakeFetchByRoute(
  statusBody: unknown,
  journalBody: unknown,
  seen: string[],
) {
  return vi.fn().mockImplementation((url: unknown) => {
    seen.push(String(url));
    const text = String(url);
    const body = text.includes("/api/v1/watcher/journal")
      ? journalBody
      : statusBody;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
  });
}

const STATUS_BODY = {
  project_id: "proj-w",
  integrity_ok: true,
  journal_head: "evt-0007",
  generated_at: "2026-10-27T00:00:00Z",
};

const JOURNAL_BODY = [
  { entry_id: "evt-0006", timestamp: "2026-10-26T00:00:00Z", hash: "h6" },
  { entry_id: "evt-0007", timestamp: "2026-10-27T00:00:00Z", hash: "h7" },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WatcherTab (fetch-level fake only)", () => {
  it("renders live status plus journal head from the two frozen GET routes", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(screen.getByTestId("watcher-project").textContent).toBe("proj-w");
    expect(screen.getByTestId("watcher-integrity").textContent).toBe("OK");
    expect(screen.getByTestId("watcher-journal-head").textContent).toBe(
      "evt-0007",
    );
    expect(screen.getByTestId("watcher-generated").textContent).toBe(
      "2026-10-27T00:00:00Z",
    );
    const journal = screen.getByTestId("watcher-journal");
    expect(journal.textContent).toContain("evt-0006");
    expect(journal.textContent).toContain("evt-0007");
    await waitFor(() => {
      expect(seen).toContain("/api/v1/watcher/status?project_id=proj-w");
      expect(seen).toContain("/api/v1/watcher/journal?project_id=proj-w");
    });
  });

  it("renders the stored failure state instead of the tab", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      }),
    );
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-error")).toBeTruthy();
    expect(screen.getByTestId("watcher-error").textContent).toContain("500");
  });

  it("defaults to the local model with cloud fallback OFF", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    const model = screen.getByTestId("watcher-model") as HTMLSelectElement;
    expect(model.value).toBe("local");
    const fallback = screen.getByTestId(
      "watcher-cloud-fallback",
    ) as HTMLInputElement;
    expect(fallback.checked).toBe(false);
  });

  it("persists settings locally and performs no other requests", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();

    const model = screen.getByTestId("watcher-model") as HTMLSelectElement;
    fireEvent.change(model, { target: { value: "API" } });
    const fallback = screen.getByTestId(
      "watcher-cloud-fallback",
    ) as HTMLInputElement;
    fireEvent.click(fallback);

    const stored = JSON.parse(
      localStorage.getItem(WATCHER_SETTINGS_KEY) ?? "{}",
    );
    expect(stored).toEqual({ model: "API", cloudFallback: true });

    cleanup();
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(
      (screen.getByTestId("watcher-model") as HTMLSelectElement).value,
    ).toBe("API");
    expect(
      (screen.getByTestId("watcher-cloud-fallback") as HTMLInputElement)
        .checked,
    ).toBe(true);

    for (const url of seen) {
      expect(
        url === "/api/v1/watcher/status?project_id=proj-w" ||
          url === "/api/v1/watcher/journal?project_id=proj-w",
      ).toBe(true);
    }
  });

  it("shows every rule card with its own area and a 20-minute hang window", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(RULE_CARDS.length).toBeGreaterThan(0);
    const areas = new Set<string>();
    for (const card of RULE_CARDS) {
      expect(
        screen.getByTestId(`rule-card-${card.cardId}-title`).textContent,
      ).toBe(card.cardId);
      const area = screen.getByTestId(`rule-card-${card.cardId}-area`)
        .textContent;
      expect(area).toBe(card.area);
      areas.add(String(area));
      expect(
        screen.getByTestId(`rule-card-${card.cardId}-hang`).textContent,
      ).toBe("20 min");
      const select = screen.getByTestId(
        `rule-card-${card.cardId}-model`,
      ) as HTMLSelectElement;
      expect(select.value).toBe("local");
      const options = Array.from(select.querySelectorAll("option")).map(
        (option) => option.value,
      );
      expect(options).toEqual([...RULE_CARD_MODELS]);
    }
    expect(areas.size).toBe(RULE_CARDS.length);
  });

  it("writes a card model choice through local settings only", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    const select = screen.getByTestId(
      "rule-card-card-guard-model",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "OFF" } });
    expect(select.value).toBe("OFF");
    expect(localStorage.getItem(cardModelKey("card-guard"))).toBe("OFF");
    for (const url of seen) {
      expect(url.startsWith("/api/v1/watcher/")).toBe(true);
    }
    expect(
      seen.every((url) => url.includes("/api/v1/watcher/status") || url.includes("/api/v1/watcher/journal")),
    ).toBe(true);
  });
});
