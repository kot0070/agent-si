// Lane A MetricCard component: collapsed one-line summary, expanded
// stacked bar plus legend plus short lists.

import type { ReactElement } from "react";
import type { MetricCardProps } from "./iface";
import { t } from "../locale/index";
import { useKitExpanded } from "./Card";

const CHART_VARS = [
  "var(--agent-si-chart-a)",
  "var(--agent-si-chart-b)",
  "var(--agent-si-chart-c)",
];

export function MetricCard(props: MetricCardProps): ReactElement {
  const title = t(props.titleKey);
  const total = t(props.totalKey);
  const [expanded, toggle] = useKitExpanded(props.collapsed, props.onToggle);
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
      <span>{title}</span>
      <button
        type="button"
        data-testid={`kit-toggle-${props.cardId}`}
        aria-label={title}
        onClick={toggle}
      >
        {title}
      </button>
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
              <span key={segment.segmentKey}>{t(segment.segmentKey)}</span>
            ))}
          </div>
          <ul data-testid="kit-expanded-list">
            {props.segments.map((segment) => (
              <li key={segment.segmentKey}>{t(segment.segmentKey)}</li>
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
