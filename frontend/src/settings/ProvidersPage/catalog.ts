// Provider catalog: base presets plus config-driven HD presets.
// Order of this array is the stable display order used by ProvidersPage.
//
// Display strings (group, keyHint, model labels) live in the locale tables
// (providers.group.*, providers.preset.<id>.keyHint, providers.model.*)
// and resolve through t() in getProviderCatalog(), so the uk page never
// renders hard-coded English. Ids, kinds, base URLs, product labels, model
// ids and key prefixes stay locale-independent by design: they are product
// names, not prose.

import { t } from "../../locale/index";
import type { ProviderPreset } from "./types";

type PresetConfig = {
  id: string;
  // Product name: identical in every locale, never translated.
  label: string;
  kind: ProviderPreset["kind"];
  groupKey: string;
  baseUrl: string;
  keyHintKey: string;
  keyStartsWith: string;
  modelLabelKeys: string[];
  // Proven model ids from src/agent_si/model_kb/loader.py, full
  // "pid/model" form; the first entry is the connect id. Presets without
  // a KB source keep the legacy model-N ids (any-openai-compatible has no KB
  // rows; local presets send no model key on connect).
  modelIds?: string[];
};

function buildPreset(config: PresetConfig): ProviderPreset {
  return {
    id: config.id,
    label: config.label,
    kind: config.kind,
    group: t(config.groupKey),
    baseUrl: config.baseUrl,
    keyHint: t(config.keyHintKey),
    keyStartsWith: config.keyStartsWith,
    models: config.modelLabelKeys.map((labelKey, index) => ({
      id: config.modelIds?.[index] ?? `${config.id}/model-${index + 1}`,
      label: t(labelKey),
    })),
  };
}

const CLOUD = "providers.group.cloud";
const COMPATIBLE = "providers.group.compatible";
const LOCAL = "providers.group.local";
const STANDARD = "providers.model.standard";
const ADVANCED = "providers.model.advanced";

function hint(id: string): string {
  return `providers.preset.${id}.keyHint`;
}

const BASE_PRESET_CONFIGS: PresetConfig[] = [
  {
    id: "meta",
    label: "Meta",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.meta.ai/v1",
    keyHintKey: hint("meta"),
    keyStartsWith: "",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["meta/muse-spark-1.3-contributor", "meta/muse-spark-1.3"],
  },
  {
    id: "openai",
    label: "OpenAI",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.openai.com/v1",
    keyHintKey: hint("openai"),
    keyStartsWith: "sk-",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["openai/gpt-4o-mini", "openai/gpt-4o"],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.anthropic.com/v1",
    keyHintKey: hint("anthropic"),
    keyStartsWith: "sk-ant-",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["anthropic/claude-haiku-4-5", "anthropic/claude-haiku-5-5"],
  },
  {
    id: "any-openai-compatible",
    label: "OpenAI-compatible",
    kind: "compatible",
    groupKey: COMPATIBLE,
    baseUrl: "http://localhost:8080/v1",
    keyHintKey: hint("any-openai-compatible"),
    keyStartsWith: "",
    modelLabelKeys: [STANDARD, ADVANCED],
  },
  {
    id: "ollama",
    label: "Ollama",
    kind: "local",
    groupKey: LOCAL,
    baseUrl: "http://localhost:11434",
    keyHintKey: hint("ollama"),
    keyStartsWith: "",
    modelLabelKeys: ["providers.model.chat", "providers.model.embeddings"],
  },
  {
    id: "lm-studio",
    label: "LM Studio",
    kind: "local",
    groupKey: LOCAL,
    baseUrl: "http://localhost:1234/v1",
    keyHintKey: hint("lm-studio"),
    keyStartsWith: "",
    modelLabelKeys: ["providers.model.chat", "providers.model.embeddings"],
  },
];

// High-demand presets, driven by this config table (not hand-built entries).
const HD_PRESET_CONFIGS: PresetConfig[] = [
  {
    id: "claude",
    label: "Claude",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.anthropic.com/v1",
    keyHintKey: hint("claude"),
    keyStartsWith: "sk-ant-",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["claude/claude-haiku-4-5", "claude/claude-haiku-5-5"],
  },
  {
    id: "gemini",
    label: "Gemini",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://generativelanguage.googleapis.com/v1beta",
    keyHintKey: hint("gemini"),
    keyStartsWith: "AIza",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["gemini/gemini-3.8-flash", "gemini/gemini-3.6-flash"],
  },
  {
    id: "mistral",
    label: "Mistral",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.mistral.ai/v1",
    keyHintKey: hint("mistral"),
    keyStartsWith: "",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["mistral/mistral-large-4", "mistral/mistral-medium-3.5"],
  },
  {
    id: "groq",
    label: "Groq",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.groq.com/openai/v1",
    keyHintKey: hint("groq"),
    keyStartsWith: "gsk-",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["groq/llama-3.3-70b-versatile", "groq/llama-3.1-8b-instant"],
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://openrouter.ai/api/v1",
    keyHintKey: hint("openrouter"),
    keyStartsWith: "sk-or-",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["openrouter/openrouter-meta-muse-spark-1.3",
               "openrouter/openrouter-qwen-qwen3.8-27b"],
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.deepseek.com/v1",
    keyHintKey: hint("deepseek"),
    keyStartsWith: "sk-",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"],
  },
  {
    id: "xai",
    label: "xAI",
    kind: "cloud",
    groupKey: CLOUD,
    baseUrl: "https://api.x.ai/v1",
    keyHintKey: hint("xai"),
    keyStartsWith: "",
    modelLabelKeys: [STANDARD, ADVANCED],
    modelIds: ["xai/grok-4.7", "xai/grok-4.6"],
  },
];

/** Locale-current catalog: call during render so t() reads the active locale. */
export function getProviderCatalog(): ProviderPreset[] {
  return [...BASE_PRESET_CONFIGS, ...HD_PRESET_CONFIGS].map(buildPreset);
}

// Import-time snapshot under the default locale (en). Kept for
// locale-independent consumers (stable ids, order, connect flow); render
// paths must use getProviderCatalog() instead.
export const PROVIDER_CATALOG: ProviderPreset[] = getProviderCatalog();

export function getPreset(catalog: ProviderPreset[], id: string): ProviderPreset | undefined {
  return catalog.find((preset) => preset.id === id);
}

export function catalogOrder(catalog: ProviderPreset[]): string[] {
  return catalog.map((preset) => preset.id);
}
