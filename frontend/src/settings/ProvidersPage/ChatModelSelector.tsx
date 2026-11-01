// ChatModelSelector: project-scoped chat model picker (frozen section 3.8 name).
// Lists enabled models only, by label. Thin wrapper over ChatSelector, which
// stays as the underlying picker so existing call sites keep working.
// The catalog and states are module defaults; the pick is uncontrolled state.
// The optional onChange reports the picked model id so the page can persist it.
// Contributor-tier data-use warning: shown verbatim directly above the picker
// whenever the picked model id maps to a warnings entry, so the warning stays
// visible without scrolling past the model name.

import { useState } from "react";
import { PROVIDER_CATALOG } from "./catalog";
import { ChatSelector } from "./ChatSelector";
import type { ProviderState } from "./types";

export const CONTRIBUTOR_MODEL_ID = "muse-spark-1.3-contributor";

export const CONTRIBUTOR_WARNING_EN =
  "Contributor tier: prompts and completions may be used by Meta to train future models (https://dev.meta.ai/docs/pricing-rate-limits).";

export const CONTRIBUTOR_WARNING_UK =
  "Тариф Contributor: запити та відповіді можуть використовуватися Meta для навчання майбутніх моделей (https://dev.meta.ai/docs/pricing-rate-limits).";

export function defaultContributorWarnings(
  lang: "en" | "uk",
): Record<string, string> {
  return {
    [CONTRIBUTOR_MODEL_ID]:
      lang === "uk" ? CONTRIBUTOR_WARNING_UK : CONTRIBUTOR_WARNING_EN,
  };
}

type ChatModelSelectorProps = {
  project_id: string;
  states?: Record<string, ProviderState>;
  onChange?: (modelId: string) => void;
  warnings?: Record<string, string>;
  lang?: "en" | "uk";
};

function warningForModel(
  table: Record<string, string>,
  modelId: string,
): string | null {
  if (!modelId) {
    return null;
  }
  const direct = table[modelId];
  if (direct) {
    return direct;
  }
  const slash = modelId.lastIndexOf("/");
  if (slash >= 0) {
    const suffix = table[modelId.slice(slash + 1)];
    if (suffix) {
      return suffix;
    }
  }
  return null;
}

export function ChatModelSelector({ project_id = "local", states = {}, onChange, warnings, lang = "en" }: ChatModelSelectorProps) {
  const catalog = PROVIDER_CATALOG;
  const [value, setValue] = useState("");
  function handleChange(modelId: string): void {
    setValue(modelId);
    if (onChange) {
      onChange(modelId);
    }
  }
  const table = { ...defaultContributorWarnings(lang), ...(warnings ?? {}) };
  const warning = warningForModel(table, value);
  return (
    <div data-testid="chat-model-selector" data-project-id={project_id}>
      {warning ? (
        <p data-testid="model-warning" role="note">
          {warning}
        </p>
      ) : null}
      <ChatSelector catalog={catalog} states={states} value={value} onChange={handleChange} />
    </div>
  );
}
