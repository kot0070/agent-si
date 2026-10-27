// Lane A Card component plus the kit-wide collapsed-state helpers.
// UI_TOKENS and collapsedStorageKey implement the matching ui/iface
// declarations; wave 3 re-exports them from the kit barrel.

import { useRef, useState } from "react";
import type { ReactElement } from "react";
import type {
  CardProps,
  CollapseToggle,
  UiTokenName,
} from "./iface";
import { t } from "../locale/index";

export const UI_TOKENS: ReadonlyArray<UiTokenName> = [
  "--agent-si-surface",
  "--agent-si-ink",
  "--agent-si-accent",
  "--agent-si-card-border",
  "--agent-si-chart-a",
  "--agent-si-chart-b",
  "--agent-si-chart-c",
];

export function collapsedStorageKey(cardId: string): string {
  return `agent-si.collapsed.${cardId}`;
}

export function useKitExpanded(
  collapsed: boolean,
  onToggle: CollapseToggle,
): [boolean, () => void] {
  const [expanded, setExpanded] = useState(!collapsed);
  const lastProp = useRef(collapsed);
  if (lastProp.current !== collapsed) {
    lastProp.current = collapsed;
    setExpanded(!collapsed);
  }
  const toggle = (): void => {
    const next = !expanded;
    setExpanded(next);
    onToggle(next);
  };
  return [expanded, toggle];
}

export function Card(props: CardProps): ReactElement {
  const title = t(props.titleKey);
  const [expanded, toggle] = useKitExpanded(props.collapsed, props.onToggle);
  return (
    <section
      data-testid={`kit-card-${props.cardId}`}
      aria-label={title}
      style={{
        backgroundColor: "var(--agent-si-surface)",
        color: "var(--agent-si-ink)",
        borderColor: "var(--agent-si-card-border)",
      }}
    >
      <span>{title}</span>
      <button
        type="button"
        data-testid={`kit-toggle-${props.cardId}`}
        aria-label={title}
        onClick={toggle}
      >
        {title}
      </button>
      {expanded ? <div>{props.children}</div> : null}
      {expanded ? null : (
        <span data-testid="kit-collapsed-line">{title}</span>
      )}
    </section>
  );
}
