/** Watcher rule cards: own area, model choice, hang window (R-364).
 *
 * Card ids follow the backend preset registry published in the CODER-1
 * RETURN (presets TABLE: card-hang, card-guard, card-tamper; the standard
 * preset installs card-hang plus card-guard). Model options and the
 * 20-minute hang default mirror the backend rule registry (MODELS
 * local/API/OFF, HANG_DEFAULT_MINUTES 20). This module carries display
 * facts only; a model choice writes through the settings module
 * (localStorage) and never performs a network call.
 */

import {
  loadCardModel,
  saveCardModel,
  type WatcherModel,
} from "./watcherSettings";

/** One rule card's display facts: its own area plus its hang window. */
export interface RuleCardSpec {
  /** Card id from the backend preset registry. */
  cardId: string;
  /** Watcher area this card alone covers. */
  area: string;
  /** Hang window in minutes; every card defaults to 20. */
  hangMinutes: number;
}

/** Default hang window in minutes carried by every rule card. */
export const HANG_DEFAULT_MINUTES = 20;

/** Every model choice one rule card may run under. */
export const RULE_CARD_MODELS: readonly WatcherModel[] = ["local", "API", "OFF"];

/** Standard rule-card set: every card carries its own area. */
export const RULE_CARDS: readonly RuleCardSpec[] = [
  { cardId: "card-hang", area: "hang", hangMinutes: HANG_DEFAULT_MINUTES },
  { cardId: "card-guard", area: "guard", hangMinutes: HANG_DEFAULT_MINUTES },
  { cardId: "card-tamper", area: "tamper", hangMinutes: HANG_DEFAULT_MINUTES },
];

/** Read one rule card's model choice (local default, never a request). */
export function cardModel(cardId: string, projectId?: string | null): WatcherModel {
  return loadCardModel(cardId, projectId);
}

/** Record one rule card's model choice locally (no network calls). */
export function setCardModel(
  cardId: string,
  model: WatcherModel,
  projectId?: string | null,
): void {
  saveCardModel(cardId, model, projectId);
}
