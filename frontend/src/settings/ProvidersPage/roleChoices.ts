// FXROLEPICK R1/R3: one shared role/chat option list.
// Providers, then each provider instance's model list: options are the
// ENABLED models as full `provider/model` ids. Ids with no `/` or
// containing `unknown` are dropped; placeholder ids (`*/model-N`) never
// reach any list; rows the KB proves pure non-text never reach a chat
// list. Labels use one style: `Provider — bare-id`.
import type { ProviderPreset, ProviderState } from "./types";
import { withConnectedSeed } from "./ChatSelector";

export type RoleModelChoice = {
  providerId: string;
  modelId: string;
  label: string;
  kb: unknown;
};

export type ChoiceModel = {
  id: string;
  label: string;
  kb?: unknown;
};

export type ChoiceCatalog = {
  id: string;
  label: string;
  models: ChoiceModel[];
};

/** Placeholder ids (`ollama/model-1`) never reach any list. */
export function isPlaceholderId(id: string): boolean {
  const tail = id.includes("/") ? (id.split("/").pop() ?? "") : id;
  return /^model-\d+$/i.test(tail.trim());
}

/** R1: an option id needs its provider part and no `unknown`. */
export function isListableModelId(id: string): boolean {
  if (!id.includes("/")) {
    return false;
  }
  if (id.toLowerCase().includes("unknown")) {
    return false;
  }
  return !isPlaceholderId(id);
}

function splitModalTokens(value: unknown): string[] {
  const text = Array.isArray(value)
    ? value.map((entry) => String(entry)).join(" ")
    : String(value ?? "");
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token !== "");
}

/** R3: chat-capable only. The KB proves a pure non-text model by a
modalities value with an image/audio/embedding token and no text
token; anything else (including no KB row) stays listable. */
export function chatCapable(kb: unknown): boolean {
  if (kb === null || kb === undefined) {
    return true;
  }
  const record = kb as Record<string, unknown>;
  const fields =
    record["fields"] !== undefined &&
    typeof record["fields"] === "object" &&
    record["fields"] !== null
      ? (record["fields"] as Record<string, unknown>)
      : record;
  const entry = fields["modalities"] as
    | { value?: unknown }
    | unknown[]
    | string
    | undefined;
  const raw =
    entry !== null &&
    typeof entry === "object" &&
    !Array.isArray(entry) &&
    "value" in (entry as Record<string, unknown>)
      ? (entry as { value?: unknown }).value
      : entry;
  if (raw === null || raw === undefined) {
    return true;
  }
  const text = Array.isArray(raw)
    ? raw.map((item) => String(item)).join(" ")
    : String(raw);
  if (text.trim() === "" || text.trim().toLowerCase() === "unknown") {
    return true;
  }
  const tokens = new Set(splitModalTokens(text));
  const nonText = tokens.has("image") ||
    tokens.has("audio") ||
    tokens.has("embedding");
  if (!nonText) {
    return true;
  }
  return tokens.has("text");
}

/** One label style: `Provider — bare-id` (never a generic word). */
export function choiceLabel(
  providerLabel: string,
  modelId: string,
): string {
  const bare = modelId.includes("/")
    ? (modelId.split("/").pop() ?? modelId)
    : modelId;
  return `${providerLabel} — ${bare}`;
}

function canonical(providerId: string, modelId: string): string {
  const prefix = `${providerId}/`;
  const bare = modelId.startsWith(prefix)
    ? modelId.slice(prefix.length)
    : modelId;
  if (bare === "" || bare.includes("/")) {
    return bare.includes("/") ? modelId : `${providerId}/${bare}`;
  }
  return `${providerId}/${bare}`;
}

/** The wizard/role/chat list: connected providers' enabled models.
States seed from the served catalog (withConnectedSeed), so a freshly
reloaded page with a connected provider still offers its models. */
export function buildRoleChoices(
  catalog: ChoiceCatalog[],
  displayModels: Record<string, ChoiceModel[]>,
  states: Record<string, ProviderState>,
): RoleModelChoice[] {
  const seeded = withConnectedSeed(catalog, states);
  const seen = new Set<string>();
  const out: RoleModelChoice[] = [];
  for (const preset of catalog) {
    const state = seeded[preset.id];
    if (state === undefined || !state.connected) {
      continue;
    }
    const enabled = new Set(
      state.enabledModels.map((id) => canonical(preset.id, id)),
    );
    for (const model of displayModels[preset.id] ?? []) {
      const full = canonical(preset.id, model.id);
      if (!enabled.has(full)) {
        continue;
      }
      if (!isListableModelId(full)) {
        continue;
      }
      if (!chatCapable(model.kb)) {
        continue;
      }
      if (seen.has(full)) {
        continue;
      }
      seen.add(full);
      out.push({
        providerId: preset.id,
        modelId: full,
        label: choiceLabel(preset.label, full),
        kb: model.kb ?? null,
      });
    }
  }
  return out;
}
