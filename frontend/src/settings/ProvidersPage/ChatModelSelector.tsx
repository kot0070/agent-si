// ChatModelSelector: project-scoped chat model picker (frozen section 3.8 name).
// Lists enabled models only, by label. Thin wrapper over ChatSelector, which
// stays as the underlying picker so existing call sites keep working.
// The catalog and states are module defaults; the pick is uncontrolled state.
// The optional onChange reports the picked model id so the page can persist it.
// Contributor-tier data-use warning: shown verbatim directly above the picker
// whenever the picked model id maps to a warnings entry, so the warning stays
// visible without scrolling past the model name.

import { useEffect, useState } from "react";
import { PROVIDER_CATALOG } from "./catalog";
import { ChatSelector, withConnectedSeed } from "./ChatSelector";
import { readChatModel } from "./modelsApi";
import { t } from "../../locale/index";
import type { ProviderPreset, ProviderState } from "./types";

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
  catalog?: ProviderPreset[];
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

function defaultLocaleWarnings(): Record<string, string> {
  return { [CONTRIBUTOR_MODEL_ID]: t("providers.chat.contributorWarning") };
}

export function ChatModelSelector({ project_id = "local", states = {}, catalog, onChange, warnings, lang = "en" }: ChatModelSelectorProps) {
  const effectiveCatalog = catalog ?? PROVIDER_CATALOG;
  // The picker reads the same merged model list the page builds (served
  // provider listing plus KB catalog); without an explicit catalog it
  // falls back to the static KB catalog.
  const resolvedCatalog = effectiveCatalog;
  const [value, setValue] = useState("");
  // FXSAVED item 1: on mount read the saved model and show it. The load
  // never fires onChange and never PUTs: it only sets local state, and
  // only while still mounted (cancelled flag).
  useEffect(() => {
    let cancelled = false;
    void readChatModel(project_id).then((saved) => {
      if (!cancelled && saved !== null && saved !== "") {
        setValue(saved);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [project_id]);
  function handleChange(modelId: string): void {
    setValue(modelId);
    if (onChange) {
      onChange(modelId);
    }
  }
  // Legacy override kept for API compatibility; the default now follows the module locale.
  void lang;
  const table = { ...defaultLocaleWarnings(), ...(warnings ?? {}) };
  const warning = warningForModel(table, value);
  return (
    <div data-testid="chat-model-selector" data-project-id={project_id}>
      {warning ? (
        <p data-testid="model-warning" role="note">
          {warning}
        </p>
      ) : null}
      <ChatSelector catalog={resolvedCatalog} states={withConnectedSeed(resolvedCatalog, states)} value={value} onChange={handleChange} />
    </div>
  );
}
