/** @vitest-environment jsdom */
// K07NEXT4 MH-5: the REAL StepTurnViewer over a fresh HttpApiClient
// (only global fetch replaced, quoting the served step turn schema
// from src/agent_si/http/k07next4.py step_turn).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { StepTurnViewer } from "../StepTurnViewer";

const SERVED_STEP_TURN = {
  row: "MH-5",
  turn: 1,
  model_input: "step mode turn 1 model input: plan the next single action",
  action: "run single tool call for turn 1",
  observation: "step mode turn 1 observation: tool result stored",
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
    if (String(input) === "/api/v1/app/step-turn?advance=1") {
      return jsonBody(SERVED_STEP_TURN);
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

describe("k07next4 MH-5 step turn over the real screen", () => {
  it("shows the model input and the observation for the turn", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <StepTurnViewer />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next4-step-turn");
    expect(seen).toContain("/api/v1/app/step-turn?advance=1");
    expect(screen.getByText(en.tasks.list.title)).toBeTruthy();
    expect(
      screen.getByText(SERVED_STEP_TURN.model_input),
    ).toBeTruthy();
    expect(screen.getByText(SERVED_STEP_TURN.observation)).toBeTruthy();
  });
});
