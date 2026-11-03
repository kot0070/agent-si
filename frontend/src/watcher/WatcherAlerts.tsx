import { useEffect, useState } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { formatScreenTime, t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import {
  fetchWatcherAlerts,
  postFireTimer,
  postIntegrityCheck,
  postPauseTimer,
  verdictLocaleKey,
  type IntegrityReportData,
  type TimerFireReceiptData,
  type TimerPauseStateData,
  type WatcherAlertRow,
} from "./watcherOps";

function toError(err: unknown): { errorKey: string; code: string } {
  const code = err instanceof ApiError ? err.code : "CONTEXT_MISSING";
  return { errorKey: apiErrorLocaleKey(code), code };
}

/** Alerts plus timers plus integrity (W3): every list loads on demand.
 *
 * Nothing fetches on mount, so the tab-level URL pins stay untouched.
 * Alerts render the served rule with plain words (never the raw enum);
 * timers fire or pause by id; the integrity check shows a plain result.
 * Every failure renders the localized ErrorPanel with Retry.
 */
export function WatcherAlerts(props: { projectId: string }): React.JSX.Element {
  const [alerts, setAlerts] = useState<WatcherAlertRow[] | null>(null);
  const [alertsError, setAlertsError] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [alertsBusy, setAlertsBusy] = useState(false);
  const [timerId, setTimerId] = useState("");
  const [reason, setReason] = useState("");
  const [timerResult, setTimerResult] = useState<
    TimerFireReceiptData | TimerPauseStateData | null
  >(null);
  const [timerError, setTimerError] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [timerBusy, setTimerBusy] = useState(false);
  const [integrity, setIntegrity] = useState<IntegrityReportData | null>(null);
  const [integrityError, setIntegrityError] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [integrityBusy, setIntegrityBusy] = useState(false);

  useEffect(() => {
    setAlerts(null);
    setAlertsError(null);
    setTimerResult(null);
    setTimerError(null);
    setIntegrity(null);
    setIntegrityError(null);
    setTimerId("");
    setReason("");
  }, [props.projectId]);

  async function loadAlerts(): Promise<void> {
    setAlertsBusy(true);
    setAlertsError(null);
    try {
      setAlerts(await fetchWatcherAlerts(props.projectId));
    } catch (err: unknown) {
      setAlertsError(toError(err));
    } finally {
      setAlertsBusy(false);
    }
  }

  async function runTimer(
    action: "fire" | "pause" | "resume",
  ): Promise<void> {
    const id = timerId.trim();
    if (id === "") {
      return;
    }
    setTimerBusy(true);
    setTimerError(null);
    try {
      if (action === "fire") {
        setTimerResult(await postFireTimer(props.projectId, id));
      } else {
        setTimerResult(
          await postPauseTimer(
            props.projectId,
            id,
            action === "pause",
            action === "pause" ? reason : "",
          ),
        );
      }
    } catch (err: unknown) {
      setTimerError(toError(err));
    } finally {
      setTimerBusy(false);
    }
  }

  async function checkIntegrity(): Promise<void> {
    setIntegrityBusy(true);
    setIntegrityError(null);
    try {
      setIntegrity(await postIntegrityCheck(props.projectId));
    } catch (err: unknown) {
      setIntegrityError(toError(err));
    } finally {
      setIntegrityBusy(false);
    }
  }

  return (
    <section data-testid="watcher-alerts-section">
      <h3 data-testid="watcher-alerts-title">
        {t("watcher.page.alertsTitle")}
      </h3>
      <button
        type="button"
        data-testid="watcher-alerts-show"
        disabled={alertsBusy}
        onClick={() => {
          void loadAlerts();
        }}
      >
        {alerts === null
          ? t("watcher.page.showAlerts")
          : t("watcher.page.refreshAlerts")}
      </button>
      {alerts !== null ? (
        alerts.length === 0 ? (
          <p data-testid="watcher-alerts-empty">{t("watcher.page.noAlerts")}</p>
        ) : (
          <ul data-testid="watcher-alerts-list">
            {alerts.map((alert) => (
              <li
                key={alert.alert_id}
                data-testid={`watcher-alert-${alert.rule_id}`}
              >
                {alert.rule_id} · {t(verdictLocaleKey(alert.verdict))}
                {alert.detail !== "" ? ` · ${alert.detail}` : ""}
              </li>
            ))}
          </ul>
        )
      ) : null}
      {alertsError !== null ? (
        <div data-testid="watcher-alerts-error">
          <ErrorPanel
            errorKey={alertsError.errorKey}
            code={alertsError.code}
            onRetry={() => {
              void loadAlerts();
            }}
          />
        </div>
      ) : null}
      <div data-testid="watcher-timers">
        <label>
          {t("watcher.page.timerId")}
          <input
            data-testid="watcher-timer-id"
            type="text"
            value={timerId}
            onChange={(event) => {
              setTimerId(event.target.value);
            }}
          />
        </label>
        <label>
          {t("watcher.page.pauseReason")}
          <input
            data-testid="watcher-timer-reason"
            type="text"
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
        </label>
        <button
          type="button"
          data-testid="watcher-timer-fire"
          disabled={timerBusy || timerId.trim() === ""}
          onClick={() => {
            void runTimer("fire");
          }}
        >
          {t("watcher.page.fireTimer")}
        </button>
        <button
          type="button"
          data-testid="watcher-timer-pause"
          disabled={timerBusy || timerId.trim() === ""}
          onClick={() => {
            void runTimer("pause");
          }}
        >
          {t("watcher.page.pauseTimer")}
        </button>
        <button
          type="button"
          data-testid="watcher-timer-resume"
          disabled={timerBusy || timerId.trim() === ""}
          onClick={() => {
            void runTimer("resume");
          }}
        >
          {t("watcher.page.resumeTimer")}
        </button>
        {timerResult !== null ? (
          <p data-testid="watcher-timer-result">
            {timerResult.timer_id} ·{" "}
            {"event" in timerResult
              ? timerResult.event
              : timerResult.paused
                ? t("watcher.page.pauseTimer")
                : t("watcher.page.resumeTimer")}{" "}
            · {t("watcher.page.journalRow")}:{" "}
            {"journal_entry_id" in timerResult
              ? timerResult.journal_entry_id
              : t("watcher.tab.notKnown")}
          </p>
        ) : null}
        {timerError !== null ? (
          <div data-testid="watcher-timer-error">
            <ErrorPanel
              errorKey={timerError.errorKey}
              code={timerError.code}
              onRetry={() => {
                void runTimer("fire");
              }}
            />
          </div>
        ) : null}
      </div>
      <div data-testid="watcher-integrity-box">
        <button
          type="button"
          data-testid="watcher-integrity-check"
          disabled={integrityBusy}
          onClick={() => {
            void checkIntegrity();
          }}
        >
          {t("watcher.page.checkIntegrity")}
        </button>
        {integrity !== null ? (
          <p data-testid="watcher-integrity-result">
            {integrity.ok
              ? t("watcher.page.integrityOk")
              : t("watcher.page.integrityMismatch")}
            {integrity.mismatched_refs.length > 0
              ? ` (${integrity.mismatched_refs.join(", ")})`
              : ""}
            {integrity.checked_at !== ""
              ? ` · ${formatScreenTime(integrity.checked_at)}`
              : ""}
          </p>
        ) : null}
        {integrityError !== null ? (
          <div data-testid="watcher-integrity-error">
            <ErrorPanel
              errorKey={integrityError.errorKey}
              code={integrityError.code}
              onRetry={() => {
                void checkIntegrity();
              }}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
