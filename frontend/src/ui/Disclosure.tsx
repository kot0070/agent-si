// Lane A Disclosure component: one-line summary plus expandable detail.

import type { ReactElement } from "react";
import type { DisclosureProps } from "./iface";
import { t } from "../locale/index";
import { useKitExpanded } from "./Card";

export function Disclosure(props: DisclosureProps): ReactElement {
  const summary = t(props.summaryKey);
  const [expanded, toggle] = useKitExpanded(!props.expanded, props.onToggle);
  return (
    <section
      data-testid={`kit-disclosure-${props.disclosureId}`}
      aria-label={summary}
    >
      <button
        type="button"
        data-testid={`kit-toggle-${props.disclosureId}`}
        aria-label={summary}
        onClick={toggle}
      >
        {summary}
      </button>
      {expanded ? (
        <div data-testid="kit-disclosure-body">{props.children}</div>
      ) : (
        <span data-testid="kit-collapsed-line">{summary}</span>
      )}
    </section>
  );
}
