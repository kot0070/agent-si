/** Per-project watcher overrides: on/off, power, signal target.
 *
 * Local preferences only (localStorage, per project): the project-level
 * watcher switch, and per rule card its on/off flag, its allowed power
 * and whom it signals. The card model select already lives in the tab
 * (watcherSettings) and is not duplicated here. Switching a preset
 * (watcherPresets) flips the on/off flags to match the preset's cards.
 * The Evaluate control stays disabled unless the project switch and the
 * card flag are both on.
 */

/** Allowed power of one rule card (BUILD_PLAN K08 ladder). */
export type WatcherPower = "observe" | "restart-once" | "pause" | "stop";

/** Hierarchy level one rule card signals. */
export type SignalTarget = "manager" | "director" | "user";

/** Every power choice the UI may offer, weakest first. */
export const WATCHER_POWERS: readonly WatcherPower[] = [
  "observe",
  "restart-once",
  "pause",
  "stop",
];

/** Every signal target the UI may offer. */
export const SIGNAL_TARGETS: readonly SignalTarget[] = [
  "manager",
  "director",
  "user",
];

/** Default power: observe plus notify, free of approval. */
export const DEFAULT_WATCHER_POWER: WatcherPower = "observe";

/** Default signal target: the Director role. */
export const DEFAULT_SIGNAL: SignalTarget = "director";

/** localStorage namespace for every override key. */
export const WATCHER_OVERRIDE_NAMESPACE = "agent_si.watcher.";

/** Storage key for one project's watcher on/off flag. */
export function watcherEnabledKey(projectId: string): string {
  return `${WATCHER_OVERRIDE_NAMESPACE}${projectId}.enabled`;
}

/** Storage key for one rule card's on/off flag. */
export function cardEnabledKey(cardId: string, projectId: string): string {
  return `${WATCHER_OVERRIDE_NAMESPACE}${projectId}.card.${cardId}.enabled`;
}

/** Storage key for one rule card's allowed power. */
export function cardPowerKey(cardId: string, projectId: string): string {
  return `${WATCHER_OVERRIDE_NAMESPACE}${projectId}.card.${cardId}.power`;
}

/** Storage key for one rule card's signal target. */
export function cardSignalKey(cardId: string, projectId: string): string {
  return `${WATCHER_OVERRIDE_NAMESPACE}${projectId}.card.${cardId}.whom`;
}

function isPower(value: unknown): value is WatcherPower {
  return (
    value === "observe" ||
    value === "restart-once" ||
    value === "pause" ||
    value === "stop"
  );
}

function isSignal(value: unknown): value is SignalTarget {
  return value === "manager" || value === "director" || value === "user";
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

/** True unless the project watcher was switched off (default on). */
export function isWatcherEnabled(projectId: string): boolean {
  return readStored(watcherEnabledKey(projectId)) !== "off";
}

/** Record one project's watcher on/off flag locally. */
export function setWatcherEnabled(enabled: boolean, projectId: string): void {
  writeStored(watcherEnabledKey(projectId), enabled ? "on" : "off");
}

/** True unless the card was switched off (default on). */
export function isCardEnabled(cardId: string, projectId: string): boolean {
  return readStored(cardEnabledKey(cardId, projectId)) !== "off";
}

/** Record one rule card's on/off flag locally (no network calls). */
export function setCardEnabled(
  cardId: string,
  enabled: boolean,
  projectId: string,
): void {
  writeStored(cardEnabledKey(cardId, projectId), enabled ? "on" : "off");
}

/** True for every power but observe plus notify. */
export function isStrongPower(power: WatcherPower): boolean {
  return power !== "observe";
}

/** Load one rule card's allowed power; unknown reads observe. */
export function cardPower(cardId: string, projectId: string): WatcherPower {
  const raw = readStored(cardPowerKey(cardId, projectId));
  return isPower(raw) ? raw : DEFAULT_WATCHER_POWER;
}

/** Record one rule card's allowed power locally. */
export function setCardPower(
  cardId: string,
  power: WatcherPower,
  projectId: string,
): void {
  if (!isPower(power)) {
    return;
  }
  writeStored(cardPowerKey(cardId, projectId), power);
}

/** Load one rule card's signal target; unknown reads director. */
export function cardSignal(cardId: string, projectId: string): SignalTarget {
  const raw = readStored(cardSignalKey(cardId, projectId));
  return isSignal(raw) ? raw : DEFAULT_SIGNAL;
}

/** Record one rule card's signal target locally. */
export function setCardSignal(
  cardId: string,
  target: SignalTarget,
  projectId: string,
): void {
  if (!isSignal(target)) {
    return;
  }
  writeStored(cardSignalKey(cardId, projectId), target);
}
