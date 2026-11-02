// Chat model picker. Lists enabled models only: the provider must be
// connected and the model toggled on. Display shows labels, never raw ids.

import type { ProviderPreset, ProviderState } from "./types";
import { t } from "../../locale/index";

export type ChatChoice = {
  providerId: string;
  modelId: string;
  label: string;
};

export function enabledChatChoices(
  catalog: ProviderPreset[],
  states: Record<string, ProviderState>,
): ChatChoice[] {
  const out: ChatChoice[] = [];
  for (const preset of catalog) {
    const state = states[preset.id];
    if (!state || !state.connected) {
      continue;
    }
    for (const model of preset.models) {
      if (state.enabledModels.includes(model.id)) {
        out.push({
          providerId: preset.id,
          modelId: model.id,
          label: `${preset.label} \u2014 ${model.label}`,
        });
      }
    }
  }
  return out;
}

// W12: served-connected providers seed the chat select. A provider the
// routes already know as connected but with no explicit model picks yet
// contributes its full catalog model list, so the picker is never empty
// right after connect. Explicit picks are never overridden.
export function withConnectedSeed(
  catalog: ProviderPreset[],
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
      {value === "" && choices.length > 0 ? (
        <p data-testid="chat-model-empty">
          {label}: {placeholder}
        </p>
      ) : null}
    </label>
  );
}
