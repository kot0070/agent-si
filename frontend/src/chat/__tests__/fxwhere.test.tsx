/** @vitest-environment jsdom */
// FXWHERE RED-first: the Done line says WHERE the files went.
// `files: koreva.txt, in <project folder>` with the path; the open-folder
// action stays. Folder source is the runs ledger (run_id -> folder), no
// stream change. FAKE seam only at fetch; the page and the verdict are real.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import {
  ChatArea,
  EngineTurnView,
  engineVerdictLine,
  summarizeEngineTurn,
} from "../index";

const PROJECT = "p-fxwhere";
const FOLDER = "D:\\agent-si-proj";
const RUN_ID = "run-fxwhere-1";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let historyTurns: unknown[];

function stubBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.startsWith("/api/v1/chat/history")) {
      if (method === "POST") {
        return jsonBody({ ok: true });
      }
      return jsonBody({ turns: historyTurns });
    }
    if (url.startsWith("/api/v1/runs/ledger")) {
      return jsonBody({
        rows: [],
        runs: [{ run_id: RUN_ID, folder: FOLDER, success: true }],
      });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: PROJECT, models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    return jsonBody({ code: "FXWHERE_UNEXPECTED_API" }, 404);
  });
}

function engineText(): string {
  return (
    "Working folder: agent-si-proj\n" +
    "Director: plan of 1 parts\n" +
    "Part p1: Create file koreva.txt with the text hello [files: koreva.txt]\n" +
    "Part p1: PASS (checks green, auditor PASS)\n" +
    "run success: all 1 parts PASS\n"
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  historyTurns = [];
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXWHERE verdict names the project folder", () => {
  it("verdict lists files with the folder when known", () => {
    const summary = summarizeEngineTurn(engineText(), "ok", FOLDER);
    const line = engineVerdictLine(summary);
    expect(line).toContain("files: koreva.txt, in " + FOLDER);
  });

  it("verdict keeps the old text when the folder is unknown", () => {
    const summary = summarizeEngineTurn(engineText(), "ok");
    expect(engineVerdictLine(summary, "")).toBe(
      "Done — 1 part, 1 passed, files: koreva.txt.",
    );
  });

  it("verdict redacts the user profile segment but keeps the folder", () => {
    const summary = summarizeEngineTurn(
      engineText(),
      "ok",
      "C:\\Users\\Ivan\\proj",
    );
    const line = engineVerdictLine(summary);
    expect(line).toContain("in ~\\proj");
    expect(line).not.toContain("Ivan");
  });

  it("real EngineTurnView render shows where the file went", async () => {
    render(
      <EngineTurnView text={engineText()} status="ok" folder={FOLDER} />,
    );
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain(
      "files: koreva.txt, in " + FOLDER,
    );
  });

  it("real EngineTurnView render without folder keeps the old line", async () => {
    render(<EngineTurnView text={engineText()} status="ok" />);
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toBe(
      "Done — 1 part, 1 passed, files: koreva.txt.",
    );
  });

  it("real chat page resolves the folder from the runs ledger", async () => {
    historyTurns = [
      {
        project_id: PROJECT,
        user_text: "make a file on disk D root koreva.txt hello",
        assistant_text: engineText(),
        time: "2026-01-01T00:00:00Z",
        id: "t-fxwhere-1",
        status: "ok",
        run_id: RUN_ID,
        executed: true,
        run_end_reason: "",
      },
    ];
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT} />
      </ApiClientProvider>,
    );
    const verdict = await screen.findByTestId("run-verdict");
    await vi.waitFor(() => {
      expect(verdict.textContent).toContain(
        "files: koreva.txt, in " + FOLDER,
      );
    });
  });
});
