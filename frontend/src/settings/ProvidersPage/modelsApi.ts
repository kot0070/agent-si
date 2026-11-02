// Provider model listings: the served provider row plus the KB catalog.
// A connected provider lists every model known from two sources, in this
// order: (1) the provider's own served listing GET
// /api/v1/providers/{id}/models (KB-backed on the served app: the rows the
// routes know for this provider), then (2) the KB-derived static catalog
// entries (PROVIDER_CATALOG) not already listed. Nothing is invented: ids
// come only from those two sources. Price shows when the served row
// carries price info, otherwise the literal "not known" (locale files are
// frozen for this lane, so UI fallback strings stay literals).
//
// New-shape payloads ({models:[{id,name,price,kb_known}], source, enabled})
// are read verbatim; the current shape ({models:[{model,enabled,in_base,kb}]})
// is adapted (bare KB ids qualify against the catalog, kb_known falls back
// to in_base). The served `enabled` array, when present, is the routing
// truth; otherwise only the default model starts ticked.

import { requestResponse } from "../../api/errors";

export type ServedModelRow = {
  model: string;
  enabled: boolean;
  in_base: boolean;
  kb: unknown;
};

// One display row for the step-2 model list.
export type ProviderModelRow = {
  id: string;
  label: string;
  kb: unknown;
  // Served price (a number, a pair string, or null) when the route names it.
  price: unknown;
  // True when the capability base knows the model, false when it does not,
  // null when the route says nothing usable.
  kbKnown: boolean | null;
};

export type ProviderModelsOutcome = {
  rows: ProviderModelRow[];
  // Where the list came from: the live provider listing, or the known
  // (catalog) list when the live list failed or came back empty.
  source: "provider" | "catalog";
  // Served tick truth when the route names it, else null (the caller ticks
  // the default model only).
  servedEnabled: string[] | null;
};

// GET one provider's own model listing. Never throws: an unknown provider,
// a missing route, or any failure yields [] (the catalog half still lists).
export async function listServedModels(providerId: string): Promise<ServedModelRow[]> {
  try {
    const response = await requestResponse(
      `/api/v1/providers/${encodeURIComponent(providerId)}/models`,
      { method: "GET" },
    );
    const data: unknown = await response.json();
    if (!isRecord(data) || !Array.isArray(data["models"])) {
      return [];
    }
    const rows: ServedModelRow[] = [];
    for (const row of data["models"] as unknown[]) {
      if (!isRecord(row) || typeof row["model"] !== "string") {
        continue;
      }
      rows.push({
        model: row["model"] as string,
        enabled: row["enabled"] === true,
        in_base: row["in_base"] === true,
        kb: row["kb"] ?? null,
      });
    }
    return rows;
  } catch {
    return [];
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function numericPrice(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function kbField(kb: unknown, name: string): unknown {
  // Served rows carry kb as null today (the served models port passes plain
  // id strings); KB-bound deployments may carry a fields mapping instead.
  if (!isRecord(kb)) {
    return null;
  }
  const fields = isRecord(kb["fields"]) ? (kb["fields"] as Record<string, unknown>) : kb;
  const entry = fields[name];
  if (isRecord(entry) && "value" in entry) {
    return entry["value"];
  }
  return entry ?? null;
}

// Price cell text for one model row: the served price (a number, or a
// "a/b" pair string) when the row carries it, else KB input/output prices
// when carried, else the literal "not known".
export function modelPriceText(kb: unknown, price?: unknown): string {
  const direct = numericPrice(price);
  if (direct !== null) {
    return `$${direct}`;
  }
  if (typeof price === "string" && price.trim() !== "") {
    return price.trim();
  }
  const input = numericPrice(kbField(kb, "input_token_price"));
  const output = numericPrice(kbField(kb, "output_token_price"));
  if (input !== null || output !== null) {
    const show = (value: number | null): string =>
      value === null ? "?" : String(value);
    return `$${show(input)}/$${show(output)}`;
  }
  return "not known";
}

// Full step-2 listing for one provider: live rows merged over the catalog,
// the list source, and the served tick truth when the route names it.
// Never throws: any failure yields the catalog list with source "catalog".
export async function listProviderModels(
  providerId: string,
  catalogModels: Array<{ id: string; label: string }>,
): Promise<ProviderModelsOutcome> {
  const fallback: ProviderModelsOutcome = {
    rows: catalogModels.map((entry) => ({
      id: entry.id,
      label: entry.label,
      kb: null,
      price: null,
      kbKnown: null,
    })),
    source: "catalog",
    servedEnabled: null,
  };
  let data: unknown;
  try {
    const response = await requestResponse(
      `/api/v1/providers/${encodeURIComponent(providerId)}/models`,
      { method: "GET" },
    );
    data = await response.json();
  } catch {
    return fallback;
  }
  if (!isRecord(data) || !Array.isArray(data["models"])) {
    return fallback;
  }
  const raw = data["models"] as unknown[];
  if (raw.length === 0) {
    return fallback;
  }
  const catalogIds = new Set(catalogModels.map((entry) => entry.id));
  const seen = new Set<string>();
  const rows: ProviderModelRow[] = [];
  for (const item of raw) {
    if (!isRecord(item)) {
      continue;
    }
    // New shape names id/name/price/kb_known; the current shape names
    // model with label in_base/kb beside it.
    const servedId =
      typeof item["id"] === "string"
        ? (item["id"] as string)
        : typeof item["model"] === "string"
          ? (item["model"] as string)
          : null;
    if (servedId === null || servedId === "") {
      continue;
    }
    const qualified =
      servedId.includes("/") || providerId === ""
        ? servedId
        : `${providerId}/${servedId}`;
    const id = catalogIds.has(servedId)
      ? servedId
      : catalogIds.has(qualified)
        ? qualified
        : servedId;
    if (seen.has(id)) {
      continue;
    }
    seen.add(id);
    const catalogEntry = catalogModels.find((entry) => entry.id === id);
    const label =
      typeof item["name"] === "string" && (item["name"] as string) !== ""
        ? (item["name"] as string)
        : (catalogEntry?.label ?? id);
    const kb = item["kb"] ?? null;
    const kbKnown =
      typeof item["kb_known"] === "boolean"
        ? (item["kb_known"] as boolean)
        : typeof item["in_base"] === "boolean"
          ? (item["in_base"] as boolean)
          : null;
    const price = "price" in item ? item["price"] : null;
    rows.push({ id, label, kb, price: price ?? null, kbKnown });
  }
  if (rows.length === 0) {
    return fallback;
  }
  const enabled = Array.isArray(data["enabled"])
    ? (data["enabled"] as unknown[]).filter(
        (entry): entry is string => typeof entry === "string",
      )
    : null;
  const declared = data["source"] === "provider" || data["source"] === "catalog"
    ? (data["source"] as "provider" | "catalog")
    : "provider";
  return { rows, source: declared, servedEnabled: enabled };
}

// Merge served ids with catalog models: served order first, then catalog
// entries not already listed. Labels come from the catalog when the id is
// known there, otherwise the id itself (never an invented label).
// Served spellings are bare KB ids ("gpt-4o-mini") while the catalog (and
// the connect POST) uses qualified ids ("openai/gpt-4o-mini"): a bare
// served id that qualifies to a catalog entry of this provider joins that
// entry, so one model never lists twice. Genuinely new served ids stay
// verbatim (they come from the route, never invented here).
export function mergeModelList(
  catalogModels: Array<{ id: string; label: string }>,
  served: ServedModelRow[],
  providerId: string,
): Array<{ id: string; label: string; kb: unknown }> {
  const catalogIds = new Set(catalogModels.map((entry) => entry.id));
  const seen = new Set<string>();
  const out: Array<{ id: string; label: string; kb: unknown }> = [];
  for (const row of served) {
    const qualified =
      row.model.includes("/") || providerId === ""
        ? row.model
        : `${providerId}/${row.model}`;
    const id = catalogIds.has(row.model)
      ? row.model
      : catalogIds.has(qualified)
        ? qualified
        : row.model;
    if (seen.has(id)) {
      continue;
    }
    seen.add(id);
    const catalogEntry = catalogModels.find((entry) => entry.id === id);
    out.push({ id, label: catalogEntry?.label ?? id, kb: row.kb });
  }
  for (const entry of catalogModels) {
    if (seen.has(entry.id)) {
      continue;
    }
    seen.add(entry.id);
    out.push({ id: entry.id, label: entry.label, kb: null });
  }
  return out;
}
