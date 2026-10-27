// Lane A unsaved-edit guard: wraps routed content and, while armed,
// blocks router navigation plus tab close behind a confirm dialog with
// Stay and Leave actions.

import { useEffect } from "react";
import type { ReactElement } from "react";
import { useBlocker } from "react-router-dom";
import type { ClosingGuardProps } from "../app/iface";
import { t } from "../locale/index";

export function ClosingGuard(props: ClosingGuardProps): ReactElement {
  const blocker = useBlocker(props.armed);

  useEffect(() => {
    if (!props.armed) {
      return;
    }
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [props.armed]);

  return (
    <>
      {props.children}
      {blocker.state === "blocked" ? (
        <div
          data-testid="closing-confirm"
          role="alertdialog"
          aria-label={t(props.confirmKey)}
        >
          <p>{t(props.confirmKey)}</p>
          <button
            type="button"
            data-testid="closing-stay"
            onClick={() => {
              blocker.reset();
            }}
          >
            {t("shell.closing.stay")}
          </button>
          <button
            type="button"
            data-testid="closing-leave"
            onClick={() => {
              blocker.proceed();
            }}
          >
            {t("shell.closing.leave")}
          </button>
        </div>
      ) : null}
    </>
  );
}
