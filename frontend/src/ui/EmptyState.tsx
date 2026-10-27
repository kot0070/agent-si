// Lane A EmptyState component: localized empty message plus an optional
// localized action button.

import type { ReactElement } from "react";
import type { EmptyStateProps } from "./iface";
import { t } from "../locale/index";

export function EmptyState(props: EmptyStateProps): ReactElement {
  const message = t(props.stateKey);
  return (
    <div data-testid="kit-empty-state">
      <p>{message}</p>
      {props.actionKey !== null && props.onAction !== null ? (
        <button
          type="button"
          data-testid="kit-empty-action"
          onClick={props.onAction}
        >
          {t(props.actionKey)}
        </button>
      ) : null}
    </div>
  );
}
