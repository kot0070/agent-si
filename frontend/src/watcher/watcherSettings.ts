/** Watcher tab settings: local defaults, persisted locally only.
 *
 * Closes R-336 on the settings side: the watcher serves the local model
 * by default and the cloud fallback stays OFF until the user opts in.
 * Every setting persists in localStorage under the `agent_si.watcher.*`
 * namespace. This module never performs network calls, so recording a
 * choice here exfiltrates nothing.
 */

/** Model a watcher rule card may run under. Mirrors the backend MODELS. */
export type WatcherModel = "local" | "API" | "OFF";

/** Persisted watcher settings record. */
export interface WatcherSettings {
  /** Serving model: the local-AI default. */
  model: WatcherModel;
  /** Cloud-fallback switch: OFF default. */
  cloudFallback: boolean;
}

/** localStorage namespace for every watcher setting key. */
export const WATCHER_SETTINGS_NAMESPACE = "agent_si.watcher.";

/** Storage key for the tab-level watcher settings record (legacy, project-less). */
export const WATCHER_SETTINGS_KEY = `${WATCHER_SETTINGS_NAMESPACE}settings`;

/** Storage key for one project's tab-level watcher settings record. */
export function watcherSettingsKey(projectId: string): string {
  return `${WATCHER_SETTINGS_NAMESPACE}${projectId}.settings`;
}

/** Storage key prefix for one rule card's model choice. */
export const WATCHER_CARD_MODEL_PREFIX = `${WATCHER_SETTINGS_NAMESPACE}card.`;

/** Storage key suffix for one rule card's model choice. */
export const WATCHER_CARD_MODEL_SUFFIX = ".model";

/** R-336 defaults: local AI, cloud fallback OFF. */
export const DEFAULT_WATCHER_SETTINGS: WatcherSettings = {
  model: "local",
  cloudFallback: false,
};

/** Every model choice the UI may offer. */
export const WATCHER_MODELS: readonly WatcherModel[] = ["local", "API", "OFF"];

function isWatcherModel(value: unknown): value is WatcherModel {
  return value === "local" || value === "API" || value === "OFF";
}

function readStored(key: string): string | null {
  try {
    if (typeof localStorage === "undefined") {
      return null;
    }
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    if (typeof localStorage === "undefined") {
      return;
    }
    localStorage.setItem(key, value);
  } catch {
    return;
  }
}

/** One stored key read: the project key, else one read of the old key. */
function readProjectOrLegacy(projectKey: string, legacyKey: string): string | null {
  const raw = readStored(projectKey);
  if (raw !== null) {
    return raw;
  }
  return readStored(legacyKey);
}

/** Load the tab settings; unknown or missing fields fall back to defaults. */
export function loadWatcherSettings(projectId?: string | null): WatcherSettings {
  const raw = projectId
    ? readProjectOrLegacy(watcherSettingsKey(projectId), WATCHER_SETTINGS_KEY)
    : readStored(WATCHER_SETTINGS_KEY);
  if (raw === null) {
    return { ...DEFAULT_WATCHER_SETTINGS };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...DEFAULT_WATCHER_SETTINGS };
  }
  if (typeof parsed !== "object" || parsed === null) {
    return { ...DEFAULT_WATCHER_SETTINGS };
  }
  const record = parsed as Record<string, unknown>;
  return {
    model: isWatcherModel(record["model"])
      ? record["model"]
      : DEFAULT_WATCHER_SETTINGS.model,
    cloudFallback:
      typeof record["cloudFallback"] === "boolean"
        ? record["cloudFallback"]
        : DEFAULT_WATCHER_SETTINGS.cloudFallback,
  };
}

/** Persist the tab settings locally (per project when given). */
export function saveWatcherSettings(
  settings: WatcherSettings,
  projectId?: string | null,
): void {
  const record: WatcherSettings = {
    model: isWatcherModel(settings.model)
      ? settings.model
      : DEFAULT_WATCHER_SETTINGS.model,
    cloudFallback: settings.cloudFallback === true,
  };
  writeStored(
    projectId ? watcherSettingsKey(projectId) : WATCHER_SETTINGS_KEY,
    JSON.stringify(record),
  );
}

/** Record the tab-level model choice locally; returns the stored settings. */
export function setWatcherModel(
  model: WatcherModel,
  projectId?: string | null,
): WatcherSettings {
  const next: WatcherSettings = { ...loadWatcherSettings(projectId), model };
  saveWatcherSettings(next, projectId);
  return next;
}

/** Record the cloud-fallback switch locally; returns the stored settings. */
export function setCloudFallback(
  enabled: boolean,
  projectId?: string | null,
): WatcherSettings {
  const next: WatcherSettings = {
    ...loadWatcherSettings(projectId),
    cloudFallback: enabled === true,
  };
  saveWatcherSettings(next, projectId);
  return next;
}

/** Storage key for one rule card's model choice (per project when given). */
export function cardModelKey(cardId: string, projectId?: string | null): string {
  if (projectId) {
    return `${WATCHER_SETTINGS_NAMESPACE}${projectId}.card.${cardId}.model`;
  }
  return `${WATCHER_CARD_MODEL_PREFIX}${cardId}${WATCHER_CARD_MODEL_SUFFIX}`;
}

/** Load one rule card's model choice; defaults to the local model. */
export function loadCardModel(
  cardId: string,
  projectId?: string | null,
): WatcherModel {
  const key = projectId ? cardModelKey(cardId, projectId) : cardModelKey(cardId);
  let raw = readStored(key);
  if (raw === null && projectId) {
    raw = readStored(cardModelKey(cardId));
  }
  return isWatcherModel(raw) ? raw : "local";
}

/** Persist one rule card's model choice locally (no network calls). */
export function saveCardModel(
  cardId: string,
  model: WatcherModel,
  projectId?: string | null,
): void {
  if (!isWatcherModel(model)) {
    return;
  }
  writeStored(
    projectId ? cardModelKey(cardId, projectId) : cardModelKey(cardId),
    model,
  );
}
