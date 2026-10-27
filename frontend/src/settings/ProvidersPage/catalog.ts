// Provider catalog: base presets plus config-driven HD presets.
// Order of this array is the stable display order used by ProvidersPage.

import type { ProviderPreset } from "./types";

type PresetConfig = {
  id: string;
  label: string;
  kind: ProviderPreset["kind"];
  group: string;
  baseUrl: string;
  keyHint: string;
  keyStartsWith: string;
  modelLabels: string[];
};

function buildPreset(config: PresetConfig): ProviderPreset {
  return {
    id: config.id,
    label: config.label,
    kind: config.kind,
    group: config.group,
    baseUrl: config.baseUrl,
    keyHint: config.keyHint,
    keyStartsWith: config.keyStartsWith,
    models: config.modelLabels.map((label, index) => ({
      id: `${config.id}/model-${index + 1}`,
      label,
    })),
  };
}

const BASE_PRESETS: PresetConfig[] = [
  {
    id: "meta",
    label: "Meta",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.llama.com/v1",
    keyHint: "Key from your Meta dashboard.",
    keyStartsWith: "",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "openai",
    label: "OpenAI",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.openai.com/v1",
    keyHint: "Starts with sk-.",
    keyStartsWith: "sk-",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.anthropic.com/v1",
    keyHint: "Starts with sk-ant-.",
    keyStartsWith: "sk-ant-",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "openai-compatible",
    label: "OpenAI-compatible",
    kind: "compatible",
    group: "Compatible",
    baseUrl: "http://localhost:8080/v1",
    keyHint: "Any OpenAI-style key or token for your server.",
    keyStartsWith: "",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "ollama",
    label: "Ollama",
    kind: "local",
    group: "Local",
    baseUrl: "http://localhost:11434",
    keyHint: "Local server: usually no key is needed.",
    keyStartsWith: "",
    modelLabels: ["Chat", "Embeddings"],
  },
  {
    id: "lmstudio",
    label: "LM Studio",
    kind: "local",
    group: "Local",
    baseUrl: "http://localhost:1234/v1",
    keyHint: "Local server: usually no key is needed.",
    keyStartsWith: "",
    modelLabels: ["Chat", "Embeddings"],
  },
];

// High-demand presets, driven by this config table (not hand-built entries).
const HD_PRESET_CONFIGS: PresetConfig[] = [
  {
    id: "claude",
    label: "Claude",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.anthropic.com/v1",
    keyHint: "Starts with sk-ant-.",
    keyStartsWith: "sk-ant-",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "gemini",
    label: "Gemini",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta",
    keyHint: "Key from AI Studio (starts with AIza).",
    keyStartsWith: "AIza",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "mistral",
    label: "Mistral",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.mistral.ai/v1",
    keyHint: "Key from the Mistral console.",
    keyStartsWith: "",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "groq",
    label: "Groq",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.groq.com/openai/v1",
    keyHint: "Starts with gsk-.",
    keyStartsWith: "gsk-",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://openrouter.ai/api/v1",
    keyHint: "Starts with sk-or-.",
    keyStartsWith: "sk-or-",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.deepseek.com/v1",
    keyHint: "Starts with sk-.",
    keyStartsWith: "sk-",
    modelLabels: ["Standard", "Advanced"],
  },
  {
    id: "xai",
    label: "xAI",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.x.ai/v1",
    keyHint: "Key from the xAI console.",
    keyStartsWith: "",
    modelLabels: ["Standard", "Advanced"],
  },
];

export const PROVIDER_CATALOG: ProviderPreset[] = [...BASE_PRESETS, ...HD_PRESET_CONFIGS].map(buildPreset);

export function getPreset(catalog: ProviderPreset[], id: string): ProviderPreset | undefined {
  return catalog.find((preset) => preset.id === id);
}

export function catalogOrder(catalog: ProviderPreset[]): string[] {
  return catalog.map((preset) => preset.id);
}
