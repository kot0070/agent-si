// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppsCardPage, CLOSING_PROMPT } from "./AppsCard";
import { formatScreenTime, resetLocaleForTests, setLocale } from "../locale/index";

// FAKE-OF: global fetch (fetch-level fake only)
function fakeFetchOk(body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AppsCardPage (fetch-level fake only)", () => {
  it("renders stored facts for an active project", async () => {
    const fetchMock = fakeFetchOk({
      project_id: "proj-a",
      service_ids: ["svc-api"],
      paused: false,
      generated_at: "2026-10-27T00:00:00Z",
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AppsCardPage projectId="proj-a" />);
    expect(await screen.findByTestId("apps-card")).toBeTruthy();
    expect(screen.getByTestId("apps-card-project").textContent).toBe("proj-a");
    expect(screen.getByTestId("apps-card-paused").textContent).toBe("Active");
    expect(screen.getByTestId("apps-card-services").textContent).toContain("svc-api");
    expect(screen.getByTestId("apps-card-generated").textContent).toBe(
      formatScreenTime("2026-10-27T00:00:00Z", "en"),
    );
    expect(screen.getByTestId("apps-card-closing").textContent).toBe(CLOSING_PROMPT);
    expect(fetchMock).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(String(fetchMock.mock.calls[0][0])).toContain(
        "/api/v1/apps/card?project_id=proj-a",
      ),
    );
  });

  it("renders the paused state passed through from stored facts", async () => {
    vi.stubGlobal(
      "fetch",
      fakeFetchOk({
        project_id: "proj-a",
        service_ids: ["svc-api", "svc-worker"],
        paused: true,
        generated_at: "2026-10-27T00:00:00Z",
      }),
    );
    render(<AppsCardPage projectId="proj-a" />);
    expect(await screen.findByTestId("apps-card")).toBeTruthy();
    expect(screen.getByTestId("apps-card-paused").textContent).toBe("Paused");
    const services = screen.getByTestId("apps-card-services");
    expect(services.textContent).toContain("svc-api");
    expect(services.textContent).toContain("svc-worker");
  });

  it("renders the request failure instead of the card", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      }),
    );
    render(<AppsCardPage projectId="proj-a" />);
    expect(await screen.findByTestId("apps-card-error")).toBeTruthy();
    expect(screen.getByTestId("apps-card-error").textContent).toContain("500");
  });

  it("encodes the project id in the card request", async () => {
    const fetchMock = fakeFetchOk({
      project_id: "proj a/b",
      service_ids: [],
      paused: false,
      generated_at: "2026-10-27T00:00:00Z",
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AppsCardPage projectId="proj a/b" />);
    expect(await screen.findByTestId("apps-card")).toBeTruthy();
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/api/v1/apps/card?project_id=proj%20a%2Fb",
    );
  });
});
