/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  ChatModelSelector,
  CONTRIBUTOR_WARNING_EN,
  CONTRIBUTOR_WARNING_UK,
  defaultContributorWarnings,
} from "./ChatModelSelector";
import type { ProviderState, ProviderPreset } from "./types";
import { resetLocaleForTests, setLocale } from "../../locale/index";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
});

function metaCatalog(): ProviderPreset[] {
  return [
    {
      id: "meta",
      label: "Meta",
      kind: "cloud",
      group: "Cloud",
      baseUrl: "https://api.meta.ai/v1",
      keyHint: "Key from your Meta dashboard.",
      keyStartsWith: "",
      models: [{ id: "meta/warn-model", label: "Model 1" }],
    },
  ];
}

function metaConnected(): Record<string, ProviderState> {
  return {
    meta: { presetId: "meta", connected: true, enabledModels: ["meta/warn-model"] },
  };
}

describe("ChatModelSelector contributor warning", () => {
  it("shows the verbatim contributor warning for the picked model", () => {
    render(
      <ChatModelSelector
        project_id="warn-1"
        catalog={metaCatalog()}
        states={metaConnected()}
        warnings={{ "meta/warn-model": CONTRIBUTOR_WARNING_EN }}
      />,
    );
    expect(screen.queryByTestId("model-warning")).toBeNull();
    fireEvent.change(screen.getByLabelText("Chat model"), {
      target: { value: "meta/warn-model" },
    });
    const note = screen.getByTestId("model-warning");
    expect(note.textContent).toBe(CONTRIBUTOR_WARNING_EN);
    expect(note.textContent).toBe(
      "Contributor tier: prompts and completions may be used by Meta to train future models (https://dev.meta.ai/docs/pricing-rate-limits).",
    );
  });

  it("renders the warning above the picker, never past the model name", () => {
    render(
      <ChatModelSelector
        project_id="warn-2"
        catalog={metaCatalog()}
        states={metaConnected()}
        warnings={{ "meta/warn-model": CONTRIBUTOR_WARNING_EN }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat model"), {
      target: { value: "meta/warn-model" },
    });
    const note = screen.getByTestId("model-warning");
    const select = screen.getByLabelText("Chat model");
    expect(
      note.compareDocumentPosition(select) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows the verbatim Ukrainian warning when lang is uk", () => {
    render(
      <ChatModelSelector
        project_id="warn-3"
        catalog={metaCatalog()}
        states={metaConnected()}
        warnings={{ "meta/warn-model": CONTRIBUTOR_WARNING_UK }}
        lang="uk"
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat model"), {
      target: { value: "meta/warn-model" },
    });
    expect(screen.getByTestId("model-warning").textContent).toBe(
      "Тариф Contributor: запити та відповіді можуть використовуватися Meta для навчання майбутніх моделей (https://dev.meta.ai/docs/pricing-rate-limits).",
    );
  });

  it("maps the contributor model id to the verbatim warnings by default", () => {
    expect(
      defaultContributorWarnings("en")["muse-spark-1.3-contributor"],
    ).toBe(CONTRIBUTOR_WARNING_EN);
    expect(
      defaultContributorWarnings("uk")["muse-spark-1.3-contributor"],
    ).toBe(CONTRIBUTOR_WARNING_UK);
  });

  it("never renders a reworded warning as the verbatim text", () => {
    render(
      <ChatModelSelector
        project_id="warn-4"
        catalog={metaCatalog()}
        states={metaConnected()}
        warnings={{
          "meta/warn-model":
            "Contributor tier: prompts may be reused for training.",
        }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat model"), {
      target: { value: "meta/warn-model" },
    });
    expect(screen.getByTestId("model-warning").textContent).toBe(
      "Contributor tier: prompts may be reused for training.",
    );
    expect(screen.queryByText(CONTRIBUTOR_WARNING_EN)).toBeNull();
  });
});
