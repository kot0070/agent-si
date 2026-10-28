// Lane A LoadingState component: localized loading text.

import type { ReactElement } from "react";
import type { LoadingStateProps } from "./iface";
import { t } from "../locale/index";

export function LoadingState(props: LoadingStateProps): ReactElement {
  return (
    <p data-testid="kit-loading-state">
      <span aria-hidden="true" />
      {t(props.loadingKey)}
    </p>
  );
}
