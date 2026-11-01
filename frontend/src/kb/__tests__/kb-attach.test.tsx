/** @vitest-environment jsdom */
// DEMOF11: the KB attach control renders and posts source JSON to
// POST /api/v1/kb/attach (only global fetch is stubbed).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AttachControl } from "../AttachControl";

const SOURCE = {
  kb_id: "kb-demof11-ui",
  kind: "DEV_ROLE",
  project_id: "proj-demof11-ui",
  role: "dev",
  purpose: "UI attach notes.",
};

const seen: Array<{ url: string; method: string; body: string }> = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  seen.length = 0;
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: string }) => {
      seen.push({
        url: String(input),
        method: init?.method ?? "GET",
        body: String(init?.body ?? ""),
      });
      return jsonBody(SOURCE.kb_id);
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("demof11 kb attach control", () => {
  it("renders the attach control", async () => {
    render(<AttachControl source={SOURCE} />);
    await screen.findByTestId("kb-attach-control");
    expect(screen.getByTestId("kb-attach-submit")).toBeTruthy();
  });

  it("posts source JSON to /api/v1/kb/attach", async () => {
    render(<AttachControl source={SOURCE} />);
    fireEvent.click(await screen.findByTestId("kb-attach-submit"));
    await screen.findByTestId("kb-attach-result");
    expect(seen).toHaveLength(1);
    expect(seen[0].url).toBe("/api/v1/kb/attach");
    expect(seen[0].method).toBe("POST");
    expect(JSON.parse(seen[0].body)).toEqual({ source: SOURCE });
    expect(screen.getByTestId("kb-attach-result").textContent).toBe(
      SOURCE.kb_id,
    );
  });
});
