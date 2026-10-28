// Lane A PlainText component: a single localized paragraph.

import type { ReactElement } from "react";
import type { PlainTextProps } from "./iface";
import { t } from "../locale/index";

export function PlainText(props: PlainTextProps): ReactElement {
  return <p data-testid="kit-plain-text">{t(props.textKey)}</p>;
}
