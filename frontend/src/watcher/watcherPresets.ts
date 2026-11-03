/** Watcher preset choice: local per-project preference, never a request.
 *
 * Mirrors the backend preset registry (src/agent_si/watcher/presets.py
 * TABLE: cautious installs card-hang, standard adds card-guard, strict
 * adds card-tamper; the default preset is standard). There is no preset
 * HTTP route, so the choice persists in localStorage only; switching a
 * preset flips the rule-card on/off flags (ruleOverrides) to match, and
 * the page states the change in plain words.
 */

/** Preset ids served by the backend registry. */
export type WatcherPresetId = "cautious" | "standard" | "strict";

/** Every preset choice the UI may offer, cautious first. */
export const WATCHER_PRESETS: readonly WatcherPresetId[] = [
  "cautious",
  "standard",
  "strict",
];

/** Default preset seeded on fresh projects (backend DEFAULT_PRESET). */
export const DEFAULT_WATCHER_PRESET: WatcherPresetId = "standard";

/** Preset name to the rule cards it installs (backend TABLE). */
export const PRESET_TABLE: Record<WatcherPresetId, readonly string[]> = {
  cautious: ["card-hang"],
  standard: ["card-hang", "card-guard"],
  strict: ["card-hang", "card-guard", "card-tamper"],
};

/** localStorage namespace for the per-project preset choice. */
export const WATCHER_PRESET_NAMESPACE = "agent_si.watcher.";

/** Storage key for one project's preset choice. */
export function watcherPresetKey(projectId: string): string {
  return `${WATCHER_PRESET_NAMESPACE}${projectId}.preset`;
}

function isPresetId(value: unknown): value is WatcherPresetId {
  return (
    value === "cautious" || value === "standard" || value === "strict"
  );
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

/** Load one project's preset choice; unknown or missing reads standard. */
export function loadWatcherPreset(projectId: string): WatcherPresetId {
  const raw = readStored(watcherPresetKey(projectId));
  return isPresetId(raw) ? raw : DEFAULT_WATCHER_PRESET;
}

/** Persist one project's preset choice locally (no network calls). */
export function saveWatcherPreset(
  preset: WatcherPresetId,
  projectId: string,
): void {
  if (!isPresetId(preset)) {
    return;
  }
  writeStored(watcherPresetKey(projectId), preset);
}

/** The rule cards one preset installs, from the backend TABLE. */
export function presetCards(preset: WatcherPresetId): readonly string[] {
  return PRESET_TABLE[preset] ?? [];
}
