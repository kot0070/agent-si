// Chat model picker. Lists enabled models only: the provider must be
// connected and the model toggled on. Display shows labels, never raw ids.

import type { ProviderPreset, ProviderState } from "./types";

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

type ChatSelectorProps = {
  catalog: ProviderPreset[];
  states: Record<string, ProviderState>;
  value: string;
  onChange: (modelId: string) => void;
};

export function ChatSelector({ catalog, states, value, onChange }: ChatSelectorProps) {
  const choices = enabledChatChoices(catalog, states);
  return (
    <label>
      Chat model
      <select aria-label="Chat model" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select a model</option>
        {choices.map((choice) => (
          <option key={`${choice.providerId}/${choice.modelId}`} value={choice.modelId}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}
