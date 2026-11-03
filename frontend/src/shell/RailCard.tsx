// FXFACTS F10: one shared rail header. Closed cards render exactly one
// line: icon column, title, right-aligned short value, toggle chevron in
// a fixed right column. The whole row is the toggle; the subtitle rides
// the title tooltip and never renders as text. No-data cards render the
// same row static (quiet dash, no toggle).

import type { ReactElement, ReactNode } from "react";
import { Icon } from "../ui/icons";
import type { IconName } from "../ui/icons";
import { t } from "../locale/index";

export interface RailHeadProps {
  /** Toggle button testid (omitted for the static no-data row). */
  testId?: string;
  icon: IconName;
  title: string;
  /** Title tooltip: the subtitle when one exists, else the title. */
  hint?: string;
  /** Short value at the right of the closed one-liner. */
  value: ReactNode;
  expanded: boolean;
  onToggle: () => void;
  /** Testid kept on the closed one-line wrapper (kit-collapsed-line). */
  lineTestId?: string;
  /** True renders the quiet dash row with no toggle. */
  staticRow?: boolean;
}

export function RailHead(props: RailHeadProps): ReactElement {
  const line = (
    <span
      {...(props.lineTestId === undefined
        ? {}
        : { "data-testid": props.lineTestId })}
      className="fx-rail-titlevalue"
    >
      <span className="fx-rail-title">{props.title}</span>
      <span className="fx-rail-value">{props.value}</span>
    </span>
  );
  const hint = props.hint ?? props.title;
  const head = (
    <>
      <span aria-hidden="true">
        <Icon name={props.icon} />
      </span>
      {line}
    </>
  );
  if (props.staticRow === true || props.testId === undefined) {
    return (
      <div className="fx-rail-head fx-rail-static" title={hint}>
        {head}
      </div>
    );
  }
  return (
    <button
      type="button"
      data-testid={props.testId}
      aria-label={t("ui.card.toggle")}
      aria-expanded={props.expanded}
      title={hint}
      className="fx-kit-toggle fx-rail-head"
      onClick={props.onToggle}
    >
      {head}
    </button>
  );
}
