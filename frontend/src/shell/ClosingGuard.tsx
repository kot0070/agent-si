// Lane A unsaved-edit guard: wraps routed content and, while armed,
// blocks router navigation plus tab close behind a confirm dialog with
// Stay and Leave actions.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { useBlocker, useLocation, useNavigate } from "react-router-dom";
import type { ClosingGuardProps } from "../app/iface";
import { t } from "../locale/index";

export function ClosingGuard(props: ClosingGuardProps): ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const [departed, setDeparted] = useState(false);
  const [guardedPath, setGuardedPath] = useState<string | null>(null);
  const blocker = useBlocker(props.armed && !departed);

  useEffect(() => {
    if (blocker.state === "blocked") {
      setGuardedPath(location.pathname);
    }
  }, [blocker.state, location.pathname]);

  function leave(): void {
    if (blocker.state === "blocked") {
      blocker.proceed();
    }
    setDeparted(true);
  }

  function undoLeave(): void {
    const target = guardedPath;
    setDeparted(false);
    if (target !== null) {
      navigate(target);
    } else {
      navigate(-1);
    }
  }

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
          {/* FXBTN: one spaced action row: stay is the quiet way back,
              leave is the single primary. */}
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button
            type="button"
            data-testid="closing-stay"
            data-variant="quiet"
            onClick={() => {
              blocker.reset();
            }}
          >
            {t("shell.closing.stay")}
          </button>
          <button
            type="button"
            data-testid="closing-leave"
            data-variant="primary"
            autoFocus
            onClick={leave}
          >
            {t("shell.closing.leave")}
          </button>
          </div>
        </div>
      ) : null}
      {blocker.state !== "blocked" && departed ? (
        <button type="button" data-testid="closing-undo" onClick={undoLeave}>
          {t("ui.error.retry")}
        </button>
      ) : null}
    </>
  );
}
