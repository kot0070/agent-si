import { afterEach, describe, expect, it, vi } from "vitest";
import { APPS_CARD_ROUTE, fetchAppsCard } from "./AppsCard";

// FAKE-OF: global fetch (fetch-level fake only)
function fakeFetchOk(body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("appsCard contract (facts only, fetch-level fake)", () => {
  it("uses the frozen apps-card route", () => {
    expect(APPS_CARD_ROUTE).toBe("/api/v1/apps/card");
  });

  it("passes stored facts through verbatim when active", async () => {
    const stored = {
      project_id: "proj-a",
      service_ids: ["svc-api"],
      paused: false,
      generated_at: "2026-10-27T00:00:00Z",
    };
    const fetchMock = fakeFetchOk(stored);
    vi.stubGlobal("fetch", fetchMock);
    const card = await fetchAppsCard("proj-a");
    expect(card).toEqual(stored);
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      "/api/v1/apps/card?project_id=proj-a",
    );
  });

  it("passes the paused flag through untouched", async () => {
    for (const paused of [true, false]) {
      const fetchMock = fakeFetchOk({
        project_id: "proj-a",
        service_ids: ["svc-api"],
        paused,
        generated_at: "2026-10-27T00:00:00Z",
      });
      vi.stubGlobal("fetch", fetchMock);
      const card = await fetchAppsCard("proj-a");
      expect(card.paused).toBe(paused);
      vi.unstubAllGlobals();
    }
  });

  it("carries exactly the four stored fact fields and nothing computed", async () => {
    vi.stubGlobal(
      "fetch",
      fakeFetchOk({
        project_id: "proj-a",
        service_ids: ["svc-b", "svc-a"],
        paused: true,
        generated_at: "2026-10-27T00:00:01Z",
      }),
    );
    const card = await fetchAppsCard("proj-a");
    expect(Object.keys(card).sort()).toEqual(
      ["generated_at", "paused", "project_id", "service_ids"],
    );
    expect(card.service_ids).toEqual(["svc-b", "svc-a"]);
    expect(card.generated_at).toBe("2026-10-27T00:00:01Z");
    expect(card.project_id).toBe("proj-a");
  });

  it("rejects when the card request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: () => Promise.resolve({}),
      }),
    );
    await expect(fetchAppsCard("proj-a")).rejects.toThrow("503");
  });
});
