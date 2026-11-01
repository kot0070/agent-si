// FXLAYOUT MetricCard component: collapsed one-line summary, expanded
// stacked bar plus legend plus short lists. The subtitle plus value texts
// are optional: without them the card renders exactly the kit default.

import type { ReactElement } from "react";
import type { MetricCardProps } from "./iface";
import { t } from "../locale/index";
import { useKitExpanded } from "./Card";

const CHART_VARS = [
  "var(--agent-si-chart-a)",
  "var(--agent-si-chart-b)",
  "var(--agent-si-chart-c)",
];

export interface MetricCardExtras {
  subtitleKey?: string;
  totalText?: string;
  segmentTexts?: Record<string, string>;
}

export function MetricCard(
  props: MetricCardProps & MetricCardExtras,
): ReactElement {
  const title = t(props.titleKey);
  const total = props.totalText ?? t(props.totalKey);
  const [expanded, toggle] = useKitExpanded(props.collapsed, props.onToggle);
  const segmentLabel = (segmentKey: string): string => {
    const label = t(segmentKey);
    const value = props.segmentTexts?.[segmentKey];
    return value === undefined || value === "" ? label : `${label} ${value}`;
  };
  return (
    <section
      data-testid={`kit-metric-${props.cardId}`}
      aria-label={title}
      style={{
        backgroundColor: "var(--agent-si-surface)",
        color: "var(--agent-si-ink)",
        borderColor: "var(--agent-si-card-border)",
      }}
    >
      <h2>{title}</h2>
      <button
        type="button"
        data-testid={`kit-toggle-${props.cardId}`}
        aria-label={t("ui.card.toggle")}
        aria-expanded={expanded}
        className="fx-kit-toggle"
        onClick={toggle}
      />
      {props.subtitleKey === undefined ? null : (
        <p data-testid={`kit-sub-${props.cardId}`}>{t(props.subtitleKey)}</p>
      )}
      {expanded ? (
        <div>
          <span>{total}</span>
          <div data-testid="kit-expanded-bar">
            {props.segments.map((segment, index) => (
              <div
                key={segment.segmentKey}
                aria-label={t(segment.segmentKey)}
                style={{
                  width: `${segment.fraction * 100}%`,
                  backgroundColor:
                    CHART_VARS[index % CHART_VARS.length] ??
                    "var(--agent-si-chart-a)",
                }}
              />
            ))}
          </div>
          <div data-testid="kit-expanded-legend">
            {props.segments.map((segment) => (
              <span key={segment.segmentKey}>
                {segmentLabel(segment.segmentKey)}
              </span>
            ))}
          </div>
          <ul data-testid="kit-expanded-list">
            {props.segments.map((segment) => (
              <li key={segment.segmentKey}>
                {segmentLabel(segment.segmentKey)}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <span data-testid="kit-collapsed-line">
          <span>{title}</span>
          <span>{total}</span>
        </span>
      )}
    </section>
  );
}
