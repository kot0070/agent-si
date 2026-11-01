// FXLAYOUT collapsed-state helper: per-card localStorage memory with
// storage-unavailable fallback to the card default. The key shape is the
// kit-wide collapsedStorageKey so every card shares one namespace.

import { useState } from "react";
import type { CollapseToggle } from "../ui/iface";
import { collapsedStorageKey } from "../ui/Card";

export function readCardCollapsed(
  cardId: string,
  defaultCollapsed: boolean,
): boolean {
  try {
    const raw = window.localStorage.getItem(collapsedStorageKey(cardId));
    if (raw === "true") {
      return true;
    }
    if (raw === "false") {
      return false;
    }
  } catch {
    // Storage unavailable: fall back to the card default.
  }
  return defaultCollapsed;
}

export function writeCardCollapsed(cardId: string, collapsed: boolean): void {
  try {
    window.localStorage.setItem(collapsedStorageKey(cardId), String(collapsed));
  } catch {
    // Storage unavailable: the choice applies to this mount only.
  }
}

export function useCollapsedCard(
  cardId: string,
  defaultCollapsed: boolean,
): [boolean, CollapseToggle] {
  const [collapsed, setCollapsed] = useState<boolean>(() =>
    readCardCollapsed(cardId, defaultCollapsed),
  );
  const onToggle: CollapseToggle = (expanded: boolean) => {
    const next = !expanded;
    writeCardCollapsed(cardId, next);
    setCollapsed(next);
  };
  return [collapsed, onToggle];
}
