// FXLAYOUT MetricCard component: collapsed one-line summary, expanded
// stacked bar plus legend plus short lists. FXFACTS F10: a closed card is
// exactly one header row (icon, title, short value, toggle in a fixed
// right column); the whole row is the toggle; the subtitle rides the
// title tooltip and renders only when open. No card, testid or data
// removed: kit-sub-* still exists, only open-gated.

import type { ReactElement } from "react";
import type { MetricCardProps } from "./iface";
import { t } from "../locale/index";
import { useKitExpanded } from "./Card";
import { RailHead } from "../shell/RailCard";
import type { IconName } from "./icons";

const CHART_VARS = [
  "var(--agent-si-chart-a)",
  "var(--agent-si-chart-b)",
  "var(--agent-si-chart-c)",
];

export interface MetricCardExtras {
  subtitleKey?: string;
  totalText?: string;
  segmentTexts?: Record<string, string>;
  /** Glyph in the header icon column (default "chart"). */
  icon?: IconName;
  /** Short value for the closed one-liner (defaults to the total). */
  closedValue?: string;
  /** False renders the quiet dash with no toggle ("—", no data). */
  hasData?: boolean;
}

export function MetricCard(
  props: MetricCardProps & MetricCardExtras,
): ReactElement {
  const title = t(props.titleKey);
  const subtitle =
    props.subtitleKey === undefined ? null : t(props.subtitleKey);
  const total = props.totalText ?? t(props.totalKey);
  const [expanded, toggle] = useKitExpanded(props.collapsed, props.onToggle);
  const hasData = props.hasData ?? true;
  const segmentLabel = (segmentKey: string): string => {
    const label = t(segmentKey);
    const value = props.segmentTexts?.[segmentKey];
    return value === undefined || value === "" ? label : `${label} ${value}`;
  };
  const icon = props.icon ?? "chart";
  if (!hasData) {
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
        <RailHead
          icon={icon}
          title={title}
          hint={subtitle ?? title}
          value={<>&mdash;</>}
          expanded={false}
          onToggle={() => undefined}
          staticRow
        />
      </section>
    );
  }
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
      <RailHead
        testId={`kit-toggle-${props.cardId}`}
        icon={icon}
        title={title}
        hint={subtitle ?? title}
        value={props.closedValue ?? total}
        expanded={expanded}
        onToggle={toggle}
        lineTestId={expanded ? undefined : "kit-collapsed-line"}
      />
      {expanded ? (
        <div>
          {/* FXDESIGN9: one fact once only — the closed one-liner
              already carries the total, so the open body holds just the
              breakdown (subtitle, bar, legend, list). */}
          {subtitle === null ? null : (
            <p data-testid={`kit-sub-${props.cardId}`}>{subtitle}</p>
          )}
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
          <dl data-testid="kit-expanded-list">
            {props.segments.map((segment) => (
              <div key={segment.segmentKey}>
                <dt>{t(segment.segmentKey)}</dt>
                {props.segmentTexts?.[segment.segmentKey] === undefined ||
                props.segmentTexts?.[segment.segmentKey] === "" ? null : (
                  <dd>{props.segmentTexts?.[segment.segmentKey]}</dd>
                )}
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </section>
  );
}
