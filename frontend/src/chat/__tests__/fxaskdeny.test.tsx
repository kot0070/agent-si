/** @vitest-environment jsdom */
// FXASK A3 + A7 RED: deny is never Done; held is Waiting, never Done/0-parts.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import {
  ChatArea,
  engineVerdictLine,
  markAssistantRunEnded,
  summarizeEngineTurn,
} from "../index";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXASK A3 deny is never Done", () => {
  it("denied line with files and zero parts fails, en", () => {
    const summary = summarizeEngineTurn(
      "Install permission denied for npm install\n" +
        "Part p1: refused: install permission denied for npm install\n" +
        "[files: node-add/package.json, node-add/package-lock.json]",
      "ok",
    );
    expect(summary.done).toBe(false);
    const line = engineVerdictLine(summary);
    expect(line).toBe("Stopped: you denied npm install. Nothing was installed.");
    expect(line).not.toContain("Done");
    expect(line).not.toContain("0 parts");
  });

  it("engine lowercase deny line fails with the plain command", () => {
    const summary = summarizeEngineTurn(
      "run node-add: install permission denied for npm install is-odd --save",
      "ok",
    );
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toBe(
      "Stopped: you denied npm install. Nothing was installed.",
    );
  });

  it("zero parts plus files with no engine evidence is not Done", () => {
    const summary = summarizeEngineTurn(
      "some model text\n[files: package.json, package-lock.json]",
      "ok",
    );
    expect(summary.parts).toBe(0);
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain("Nothing was built");
    expect(engineVerdictLine(summary)).not.toContain("Done");
  });

  it("denied line reads Stopped in uk", () => {
    setLocale("uk");
    const summary = summarizeEngineTurn(
      "Install permission denied for npm install",
      "ok",
    );
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain("Зупинено");
    expect(engineVerdictLine(summary)).not.toContain("Done");
  });
});

describe("FXASK A7 held run is Waiting, not Done", () => {
  it("held text renders the Waiting line, en", () => {
    const summary = summarizeEngineTurn(
      "Waiting for your permission to run npm install --save.",
      "ok",
    );
    expect(summary.done).toBe(false);
    const line = engineVerdictLine(summary);
    expect(line).toBe(
      "Waiting for your permission to run npm install --save.",
    );
    expect(line).not.toContain("0 parts");
    expect(line).not.toContain("Nothing was built");
    expect(line).not.toContain("Done");
  });

  it("engine run-held line renders Waiting too", () => {
    const summary = summarizeEngineTurn(
      "run held: waiting for your permission to run npm install",
      "ok",
    );
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain(
      "Waiting for your permission to run npm install.",
    );
  });

  it("held line reads Waiting in uk", () => {
    setLocale("uk");
    const summary = summarizeEngineTurn(
      "Waiting for your permission to run npm install --save.",
      "ok",
    );
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain("Очікування");
  });
});

describe("FXASK A7 the card closes when its run ended", () => {
  const historyBody = { turns: [] };

  function stubQuiet(): void {
    vi.stubGlobal("fetch", async (input: unknown) => {
      const url = String(input);
      if (url.includes("/api/v1/chat/history")) {
        return new Response(JSON.stringify(historyBody), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    });
  }

  function seedMirror(project: string, tool: string, message: string): void {
    window.sessionStorage.setItem(
      `fxchat.ask.p.${project}`,
      JSON.stringify({ toolName: tool, messageId: message }),
    );
  }

  function renderChat(project: string): void {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={project} />
      </ApiClientProvider>,
    );
  }

  beforeEach(() => {
    stubQuiet();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("a parked card restores while its run is still open", async () => {
    const project = "fxask-restore-live";
    seedMirror(project, "install:tool", "bubble-live-1");
    renderChat(project);
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
  });

  it("a parked card never restores after its run ended", async () => {
    const project = "fxask-restore-ended";
    const bubble = "bubble-ended-1";
    seedMirror(project, "install:tool", bubble);
    markAssistantRunEnded(bubble);
    renderChat(project);
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(
      window.sessionStorage.getItem(`fxchat.ask.p.${project}`),
    ).toBeNull();
  });
});
