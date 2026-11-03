// Lane A ErrorPanel component: localized error message, the machine code
// as record data, plus an optional retry button. The frozen props carry
// no retry label key, so the button reuses the localized message.
// FXFIRST: the raw machine code never reads as primary text (plan 866):
// the sentence shows, the code lives behind Details only.

import type { ReactElement } from "react";
import type { ErrorPanelProps } from "./iface";
import { t } from "../locale/index";

export function ErrorPanel(props: ErrorPanelProps): ReactElement {
  const message = t(props.errorKey);
  return (
    <div data-testid="kit-error-panel" role="alert">
      <p>{message}</p>
      <details>
        <summary>{t("ui.error.details")}</summary>
        <span data-testid="kit-error-code">{props.code}</span>
      </details>
      {props.onRetry !== null ? (
        <button
          type="button"
          data-testid="kit-error-retry"
          aria-label={message}
          onClick={props.onRetry}
        >
          {message}
        </button>
      ) : null}
    </div>
  );
}
