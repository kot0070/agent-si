// FXFACTS F9: one shared small CSS spinner. It renders while something
// runs (chat stream, Team now row, Agents live row, Run tab label) and
// unmounts at any end state; a run waiting for a permission click shows
// "Waiting for your answer" with no spin. Still under
// prefers-reduced-motion (a static dot).

import type { ReactElement } from "react";
import { t } from "../locale/index";

export function Spinner(props: { testId?: string }): ReactElement {
  return (
    <span
      data-testid={props.testId ?? "fx-spinner"}
      role="status"
      aria-label={t("chat.stream.spinner")}
      className="fx-spin"
    />
  );
}
