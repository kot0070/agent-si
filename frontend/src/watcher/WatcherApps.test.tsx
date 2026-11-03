// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WatcherApps } from "./WatcherApps";
import { resetLocaleForTests, setLocale } from "../locale/index";

const CARD_BODY = {
  project_id: "proj-b",
  service_ids: ["svc-api", "svc-loopback"],
  paused: false,
  generated_at: "2026-10-27T00:00:00Z",
  services: [
    { service_id: "svc-api", name: "svc-api" },
    { service_id: "svc-loopback", name: "svc-loopback" },
  ],
  safe_to_close: false,
  close_prompt: "runs still active (run-1); closing now may interrupt them",
};

const STATUS_BODY: Record<string, unknown> = {
  "svc-api": {
    service_id: "svc-api",
    state: "UP",
    timestamp: "2026-10-27T00:00:00Z",
    in_use: true,
    last_used: "2026-10-27T00:00:00Z",
    last_agent: "agent-1",
  },
  "svc-loopback": {
    service_id: "svc-loopback",
    state: "DOWN",
    timestamp: "2026-10-27T00:00:00Z",
    in_use: false,
    last_used: "2026-10-27T00:00:00Z",
    last_agent: "agent-2",
  },
};

function fakeFetch(
  seen: Array<{ url: string; method: string; body: unknown }>,
) {
  return vi.fn().mockImplementation((url: unknown, init?: unknown) => {
    const request = (init ?? {}) as { method?: string; body?: string };
    const method = request.method ?? "GET";
    let body: unknown = undefined;
    try {
      body = request.body === undefined ? undefined : JSON.parse(request.body);
    } catch {
      body = request.body;
    }
    seen.push({ url: String(url), method, body });
    const text = String(url);
    if (text.includes("/api/v1/apps/card")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(CARD_BODY),
      });
    }
    if (text.includes("/api/v1/services/") && text.includes("/status")) {
      const id = text.split("/api/v1/services/")[1]?.split("/status")[0] ?? "";
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(STATUS_BODY[id] ?? {}),
      });
    }
    if (text.includes("/api/v1/services/") && text.includes("/check")) {
      const id = text.split("/api/v1/services/")[1]?.split("/check")[0] ?? "";
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(STATUS_BODY[id] ?? {}),
      });
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      json: () => Promise.resolve({}),
    });
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("WatcherApps (RED: component missing)", () => {
  it("loads nothing on mount and renders compact service rows on demand", async () => {
    const seen: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetch(seen));
    render(<WatcherApps projectId="proj-b" />);
    expect(seen).toHaveLength(0);
    fireEvent.click(screen.getByTestId("watcher-apps-load"));
    expect(await screen.findByTestId("watcher-service-svc-api")).toBeTruthy();
    const api = screen.getByTestId("watcher-service-svc-api").textContent ?? "";
    expect(api).toContain("svc-api");
    expect(api).toContain("In use");
    expect(api).toContain("agent-1");
    const loop = screen.getByTestId("watcher-service-svc-loopback").textContent ?? "";
    expect(loop).toContain("Idle");
    expect(
      screen.getByTestId("watcher-apps-do-not-close").textContent,
    ).toContain("Do not close while in use");
  });

  it("runs a service check through the check route with the chosen kind", async () => {
    const seen: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetch(seen));
    render(<WatcherApps projectId="proj-b" />);
    fireEvent.click(screen.getByTestId("watcher-apps-load"));
    expect(await screen.findByTestId("watcher-service-svc-api")).toBeTruthy();
    fireEvent.change(screen.getByTestId("watcher-service-svc-api-kind"), {
      target: { value: "TCP" },
    });
    fireEvent.click(screen.getByTestId("watcher-service-svc-api-check"));
    await waitFor(() => {
      expect(
        seen.some(
          (call) =>
            call.url === "/api/v1/services/svc-api/check" &&
            call.method === "POST" &&
            (call.body as { check?: string }).check === "TCP",
        ),
      ).toBe(true);
    });
  });
});
