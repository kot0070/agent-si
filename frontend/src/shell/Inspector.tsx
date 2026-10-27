// Lane A compact inspector: single default tab with live agents. The tab
// content arrives as a prop from App, so this module never imports the
// agents area directly. The body is compact and self-scrolling.

import type { ReactElement, ReactNode } from "react";
import type { InspectorProps as InspectorBaseProps } from "../app/iface";
import { t } from "../locale/index";

export interface InspectorProps extends InspectorBaseProps {
  live: ReactNode;
}

export function Inspector(props: InspectorProps): ReactElement {
  return (
    <aside
      data-testid="inspector"
      aria-label={t("shell.inspector.live_agents")}
      data-project={props.projectId ?? ""}
    >
      <div role="tablist" aria-label={t("shell.inspector.live_agents")}>
        <button
          type="button"
          role="tab"
          aria-selected="true"
          data-testid="inspector-tab-live"
        >
          {t("shell.inspector.live_agents")}
        </button>
      </div>
      <div
        data-testid="inspector-scroll"
        style={{ maxHeight: "320px", overflowY: "auto" }}
      >
        {props.live}
      </div>
    </aside>
  );
}
