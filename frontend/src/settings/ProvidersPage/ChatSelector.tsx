// Chat model picker. Lists enabled models only: the provider must be
// connected and the model toggled on. Display shows labels, never raw ids.

import type { ProviderPreset, ProviderState } from "./types";
import { t } from "../../locale/index";
import { withConnectedSeed } from "./ChatSelector";
import { canonical as canonicalChoiceId, chatCapable, choiceLabel, isListableModelId } from "./roleChoices";

export type ChatChoice = {
  providerId: string;
  modelId: string;
  label: string;
  kb?: unknown;
};

// R1/R3: connected providers' enabled models as full `provider/model`
// ids, one label style (`Provider — bare-id`), placeholders and
// `unknown` ids dropped, KB-proven non-text models out of the chat
// list. Without a KB row a model stays listable (never excluded on a
// guess).
export function enabledChatChoices(
  catalog: Array<ProviderPreset | { id: string; label: string; models: Array<{ id: string; label: string; kb?: unknown }> }>,
  states: Record<string, ProviderState>,
): ChatChoice[] {
  // A freshly connected provider with no explicit picks yet
  // contributes its full model list (never an empty picker); explicit
  // picks are never overridden.
  const seeded = withConnectedSeed(catalog, states);
  const out: ChatChoice[] = [];
  for (const preset of catalog) {
    const state = seeded[preset.id];
    if (!state || !state.connected) {
      continue;
    }
    // A bare served id and its qualified form are one model.
    const enabled = new Set<string>();
    for (const id of state.enabledModels) {
      enabled.add(id);
      enabled.add(canonicalChoiceId(preset.id, id));
    }
    for (const model of preset.models) {
      if (!enabled.has(model.id) && !enabled.has(canonicalChoiceId(preset.id, model.id))) {
        continue;
      }
      if (!isListableModelId(canonicalChoiceId(preset.id, model.id))) {
        continue;
      }
      const kb = (model as { kb?: unknown }).kb ?? null;
      if (!chatCapable(kb)) {
        continue;
      }
      out.push({
        providerId: preset.id,
        modelId: canonicalChoiceId(preset.id, model.id),
        label: choiceLabel(preset.label, model.id),
        kb,
      });
    }
  }
  return out;
}

// W12: served-connected providers seed the chat select. A provider the
// routes already know as connected but with no explicit model picks yet
// contributes its full catalog model list, so the picker is never empty
// right after connect. Explicit picks are never overridden.
export function withConnectedSeed<
  T extends { id: string; models: Array<{ id: string }> },
>(
  catalog: T[],
  states: Record<string, ProviderState>,
): Record<string, ProviderState> {
  const next: Record<string, ProviderState> = { ...states };
  for (const preset of catalog) {
    const current = next[preset.id];
    if (
      current !== undefined &&
      current.connected &&
      current.enabledModels.length === 0
    ) {
      next[preset.id] = {
        ...current,
        enabledModels: preset.models.map((model) => model.id),
      };
    }
  }
  return next;
}

type ChatSelectorProps = {
  catalog: ProviderPreset[];
  states: Record<string, ProviderState>;
  value: string;
  onChange: (modelId: string) => void;
};

export function ChatSelector({ catalog, states, value, onChange }: ChatSelectorProps) {
  const choices = enabledChatChoices(catalog, states);
  const label = t("providers.chat.label");
  const placeholder = t("providers.chat.selectOption");
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{placeholder}</option>
        {choices.map((choice) => (
          <option key={`${choice.providerId}/${choice.modelId}`} value={choice.modelId}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}
