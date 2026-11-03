// FXROLEPICK R8(b): a run stopped before any model call reads its
// reason as the main line (never the no-parts sentence, never a
// generic retry line), en + uk, with a link to the fix.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import {
  EngineTurnView,
  engineVerdictLine,
  summarizeEngineTurn,
} from "../index";

const NO_PROVIDER_TEXT = [
  "Team: director, manager, worker, auditor on ollama/llama3.2 (Pinned)",
  "Connect a provider first",
].join("\n");

const NO_MODEL_TEXT = [
  "Team: director on ollama/llama3.2 (Pinned)",
  "Ollama has no model chosen",
].join("\n");

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R8 stop reason as the main line", () => {
  it("reads Connect a provider first, never the no-parts sentence", () => {
    const summary = summarizeEngineTurn(NO_PROVIDER_TEXT, "failed");
    expect(summary.stopReason).toBe("no-provider");
    expect(engineVerdictLine(summary)).toBe("Connect a provider first");
  });

  it("reads the provider no-model line with its name", () => {
    const summary = summarizeEngineTurn(NO_MODEL_TEXT, "failed");
    expect(summary.stopReason).toBe("no-model");
    expect(summary.stopProvider).toBe("Ollama");
    expect(engineVerdictLine(summary)).toBe("Ollama has no model chosen");
  });

  it("renders the reason plus the fix link under the verdict", () => {
    render(<EngineTurnView text={NO_PROVIDER_TEXT} status="failed" />);
    expect(screen.getByTestId("run-verdict").textContent).toBe(
      "Connect a provider first",
    );
    const link = screen.getByTestId("run-verdict-connect");
    expect(link.getAttribute("href")).toBe("/settings/models");
    render(<EngineTurnView text={NO_MODEL_TEXT} status="failed" />);
    const verdicts = screen.getAllByTestId("run-verdict");
    expect(verdicts[verdicts.length - 1]?.textContent).toBe(
      "Ollama has no model chosen",
    );
  });

  it("localises both lines in Ukrainian", () => {
    setLocale("uk");
    const provider = summarizeEngineTurn(NO_PROVIDER_TEXT, "failed");
    expect(engineVerdictLine(provider)).toBe(
      "Спочатку підключіть постачальника",
    );
    const model = summarizeEngineTurn(NO_MODEL_TEXT, "failed");
    expect(engineVerdictLine(model)).toBe("Для Ollama не вибрано модель");
  });
});
