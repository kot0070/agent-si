// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RULE_CARDS, RULE_CARD_MODELS } from "./ruleCards";
import {
  WATCHER_SETTINGS_KEY,
  cardModelKey,
  watcherSettingsKey,
} from "./watcherSettings";
import { WatcherTab } from "./WatcherTab";
import { formatScreenTime } from "../locale/index";

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

const JOURNAL_RICH = [
  {
    entry_id: "evt-0227",
    timestamp: "2026-11-03T03:11:42Z",
    hash: "h27",
    kind: "DEVRUN_END",
    source: "runner",
    summary: "run success: all 1 parts PASS",
    refs: ["r-1"],
  },
  {
    entry_id: "evt-0228",
    timestamp: "2026-11-03T03:11:43Z",
    hash: "h28",
    kind: "DEVRUN_END",
    source: "runner",
    summary: "run success: all 1 parts PASS",
    refs: ["r-1"],
  },
  {
    entry_id: "evt-0229",
    timestamp: "2026-11-03T03:12:00Z",
    hash: "h29",
    kind: "WATCH_DECISION",
    source: "watcher",
    summary: "rule-tamper ESCALATE no watcher model: default action",
    refs: ["rule-tamper"],
  },
];

function journalRow(id: string): string {
  const row = screen.getByTestId(`journal-row-${id}`).textContent ?? "";
  return row;
}

describe("WatcherTab F6a journal rows read as plain facts", () => {
  it("renders newest first with local time, kind and summary; id plus hash in details", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      fakeFetchByRoute(STATUS_BODY, JOURNAL_RICH, seen),
    );
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    const list = await screen.findByTestId("watcher-journal");
    const text = list.textContent ?? "";
    // Newest first: evt-0229 before evt-0228.
    expect(text.indexOf("evt-0229")).toBeLessThan(text.indexOf("evt-0228"));
    // Local time through the shared helper, never the raw stamp.
    expect(journalRow("evt-0229")).toContain(
      formatScreenTime("2026-11-03T03:12:00Z", "en"),
    );
    expect(journalRow("evt-0229")).not.toContain("2026-11-03T03:12:00Z");
    // Plain kind label and short summary.
    expect(journalRow("evt-0229")).toContain("Decision");
    expect(journalRow("evt-0229")).toContain("rule-tamper");
    expect(journalRow("evt-0227")).toContain("Run end");
    // Hash and id ride the details.
    expect(journalRow("evt-0227")).toContain("h27");
  });

  it("lists five rows with Show more for longer journals", async () => {
    const seen: string[] = [];
    const long = Array.from({ length: 7 }, (_, index) => ({
      entry_id: `evt-00${30 + index}`,
      timestamp: "2026-11-03T03:12:00Z",
      hash: `h${30 + index}`,
      kind: "SERVICE_STATE",
      source: "watcher",
      summary: `beat ${index}`,
      refs: [],
    }));
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, long, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    await screen.findByTestId("watcher-journal");
    expect(screen.queryByTestId("journal-row-evt-0030")).toBeNull();
    expect(screen.getByTestId("journal-row-evt-0036")).toBeTruthy();
    fireEvent.click(screen.getByTestId("journal-show-more"));
    expect(screen.getByTestId("journal-row-evt-0030")).toBeTruthy();
  });

  it("saves per-card check minutes through local settings, range-checked", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-w" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    const input = screen.getByTestId(
      "rule-card-card-hang-hang",
    ) as HTMLInputElement;
    expect(input.value).toBe("20");
    fireEvent.change(input, { target: { value: "5" } });
    expect(
      localStorage.getItem("agent_si.watcher.proj-w.card.card-hang.hang"),
    ).toBe("5");
    fireEvent.change(input, { target: { value: "9999" } });
    expect(
      localStorage.getItem("agent_si.watcher.proj-w.card.card-hang.hang"),
    ).toBe("1440");
    for (const url of seen) {
      // Header name read beside the two frozen watcher routes.
      expect(url.startsWith("/api/v1/watcher/") || url === "/api/v1/projects").toBe(
        true,
      );
    }
  });
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
      formatScreenTime("2026-10-27T00:00:00Z", "en"),
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
    // FXANSWER S1: the 500 maps to GENERIC_ERROR; no raw
    // "request failed: 500" reaches the screen.
    expect(
      screen.getByTestId("watcher-error").textContent,
    ).toContain("GENERIC_ERROR");
    expect(
      screen.getByTestId("watcher-error").textContent,
    ).not.toContain("request failed");
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
      localStorage.getItem(watcherSettingsKey("proj-w")) ?? "{}",
    );
    expect(stored).toEqual({ model: "API", cloudFallback: true });
    // FXHIGH-6: no leak into the old project-less key.
    expect(localStorage.getItem(WATCHER_SETTINGS_KEY)).toBeNull();

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
      // FXFACTS F6a: the header reads the stored project name (one
      // projects read beside the two frozen watcher routes).
      expect(
        url === "/api/v1/watcher/status?project_id=proj-w" ||
          url === "/api/v1/watcher/journal?project_id=proj-w" ||
          url === "/api/v1/projects",
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
      // FXFACTS F6a: the hang window is a number input saved through the
      // same local settings as the model select, range-checked.
      expect(
        (screen.getByTestId(`rule-card-${card.cardId}-hang`) as HTMLInputElement)
          .value,
      ).toBe("20");
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
    expect(localStorage.getItem(cardModelKey("card-guard", "proj-w"))).toBe(
      "OFF",
    );
    for (const url of seen) {
      // FXFACTS F6a: the header reads the stored project name (one
      // projects read beside the two frozen watcher routes).
      expect(
        url.startsWith("/api/v1/watcher/") || url === "/api/v1/projects",
      ).toBe(true);
    }
    expect(
      seen.every(
        (url) =>
          url.includes("/api/v1/watcher/status") ||
          url.includes("/api/v1/watcher/journal") ||
          url === "/api/v1/projects",
      ),
    ).toBe(true);
  });

  it("keeps separate settings values per project", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    render(<WatcherTab projectId="proj-a" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();

    fireEvent.change(screen.getByTestId("watcher-model"), {
      target: { value: "API" },
    });
    fireEvent.click(screen.getByTestId("watcher-cloud-fallback"));
    expect(JSON.parse(
      localStorage.getItem(watcherSettingsKey("proj-a")) ?? "{}",
    )).toEqual({ model: "API", cloudFallback: true });

    cleanup();
    render(<WatcherTab projectId="proj-b" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    // Project B inherits nothing from A: local default, fallback OFF.
    expect(
      (screen.getByTestId("watcher-model") as HTMLSelectElement).value,
    ).toBe("local");
    expect(
      (screen.getByTestId("watcher-cloud-fallback") as HTMLInputElement)
        .checked,
    ).toBe(false);
    fireEvent.change(screen.getByTestId("watcher-model"), {
      target: { value: "OFF" },
    });
    expect(JSON.parse(
      localStorage.getItem(watcherSettingsKey("proj-b")) ?? "{}",
    )).toEqual({ model: "OFF", cloudFallback: false });

    cleanup();
    render(<WatcherTab projectId="proj-a" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(
      (screen.getByTestId("watcher-model") as HTMLSelectElement).value,
    ).toBe("API");
    expect(
      (screen.getByTestId("watcher-cloud-fallback") as HTMLInputElement)
        .checked,
    ).toBe(true);
  });

  it("reads the old project-less key once as a fallback", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", fakeFetchByRoute(STATUS_BODY, JOURNAL_BODY, seen));
    localStorage.setItem(
      WATCHER_SETTINGS_KEY,
      JSON.stringify({ model: "API", cloudFallback: true }),
    );
    render(<WatcherTab projectId="proj-legacy" />);
    expect(await screen.findByTestId("watcher-tab")).toBeTruthy();
    expect(
      (screen.getByTestId("watcher-model") as HTMLSelectElement).value,
    ).toBe("API");
    expect(
      (screen.getByTestId("watcher-cloud-fallback") as HTMLInputElement)
        .checked,
    ).toBe(true);
    // Fallback is read-only: nothing migrates until the user saves.
    expect(localStorage.getItem(watcherSettingsKey("proj-legacy"))).toBeNull();
  });
});
