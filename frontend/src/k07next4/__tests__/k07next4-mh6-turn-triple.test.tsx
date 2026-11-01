/** @vitest-environment jsdom */
// K07NEXT4 MH-6: the REAL TurnTripleBoard over a fresh HttpApiClient
// (only global fetch replaced, quoting the served turn triple schema
// from src/agent_si/http/k07next4.py turn_triple).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { TurnTripleBoard } from "../TurnTripleBoard";

const SERVED_TURN_TRIPLE = {
  row: "MH-6",
  turns: [
    {
      plan: "stored plan ref k07next4-plan-1",
      action: "stored tool call ref k07next4-call-1",
      observation: "stored result ref k07next4-result-1",
    },
  ],
  used: 1,
  limit: 10000,
};

const seen: string[] = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  vi.stubGlobal("fetch", async (input: unknown) => {
    seen.push(String(input));
    if (String(input) === "/api/v1/app/turn-triple") {
      return jsonBody(SERVED_TURN_TRIPLE);
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next4 MH-6 turn triple over the real screen", () => {
  it("renders the stored triple with the budget counter", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <TurnTripleBoard />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next4-turn-triple");
    expect(seen).toContain("/api/v1/app/turn-triple");
    expect(screen.getByText(en.agents.live.title)).toBeTruthy();
    expect(
      screen.getByText(SERVED_TURN_TRIPLE.turns[0]?.plan ?? ""),
    ).toBeTruthy();
    expect(
      screen.getByText(SERVED_TURN_TRIPLE.turns[0]?.action ?? ""),
    ).toBeTruthy();
    expect(
      screen.getByText(SERVED_TURN_TRIPLE.turns[0]?.observation ?? ""),
    ).toBeTruthy();
    expect(screen.getByText("1/10000")).toBeTruthy();
  });
});
