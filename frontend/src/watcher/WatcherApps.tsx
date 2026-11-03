import { useEffect, useState } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { formatScreenTime, t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import {
  SERVICE_CHECK_KINDS,
  fetchAppsCardFacts,
  fetchServiceStatus,
  postServiceCheck,
  serviceStateLocaleKey,
  type AppsCardFacts,
  type ServiceCheckKind,
  type ServiceStatusData,
} from "./watcherOps";

function toError(err: unknown): { errorKey: string; code: string } {
  const code = err instanceof ApiError ? err.code : "CONTEXT_MISSING";
  return { errorKey: apiErrorLocaleKey(code), code };
}

/** Apps card plus service status (W4): compact dl rows, on demand.
 *
 * Loads the stored apps card, then one status row per served service
 * id; each row shows state, in-use versus idle, the last agent plus
 * time, and a Check control with the chosen frozen kind. Refusals
 * (protected service, wrong kind) surface as plain localized errors.
 * Disk space and detected environment have no backend route and are
 * not shown. Nothing fetches on mount.
 */
export function WatcherApps(props: { projectId: string }): React.JSX.Element {
  const [card, setCard] = useState<AppsCardFacts | null>(null);
  const [statuses, setStatuses] = useState<
    Record<string, ServiceStatusData | null>
  >({});
  const [kinds, setKinds] = useState<Record<string, ServiceCheckKind>>({});
  const [cardError, setCardError] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [rowErrors, setRowErrors] = useState<
    Record<string, { errorKey: string; code: string } | null>
  >({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setCard(null);
    setStatuses({});
    setKinds({});
    setCardError(null);
    setRowErrors({});
    setBusy({});
  }, [props.projectId]);

  async function load(): Promise<void> {
    setLoading(true);
    setCardError(null);
    try {
      const facts = await fetchAppsCardFacts(props.projectId);
      setCard(facts);
      const next: Record<string, ServiceStatusData | null> = {};
      const nextErrors: Record<string, { errorKey: string; code: string } | null> = {};
      await Promise.all(
        facts.service_ids.map(async (id) => {
          try {
            next[id] = await fetchServiceStatus(id);
            nextErrors[id] = null;
          } catch (err: unknown) {
            next[id] = null;
            nextErrors[id] = toError(err);
          }
        }),
      );
      setStatuses(next);
      setRowErrors(nextErrors);
    } catch (err: unknown) {
      setCardError(toError(err));
    } finally {
      setLoading(false);
    }
  }

  async function check(serviceId: string): Promise<void> {
    const kind: ServiceCheckKind = kinds[serviceId] ?? "HTTP";
    setBusy((prev) => ({ ...prev, [serviceId]: true }));
    setRowErrors((prev) => ({ ...prev, [serviceId]: null }));
    try {
      const status = await postServiceCheck(serviceId, kind);
      setStatuses((prev) => ({ ...prev, [serviceId]: status }));
    } catch (err: unknown) {
      setRowErrors((prev) => ({ ...prev, [serviceId]: toError(err) }));
    } finally {
      setBusy((prev) => ({ ...prev, [serviceId]: false }));
    }
  }

  return (
    <section data-testid="watcher-apps">
      <h3 data-testid="watcher-apps-title">{t("watcher.page.appsTitle")}</h3>
      <button
        type="button"
        data-testid="watcher-apps-load"
        disabled={loading}
        onClick={() => {
          void load();
        }}
      >
        {t("watcher.page.loadApps")}
      </button>
      {card !== null ? (
        <>
          <p data-testid="watcher-apps-safe">
            {card.safe_to_close
              ? t("watcher.page.safeToClose")
              : t("watcher.page.doNotClose")}
            {card.safe_to_close || card.close_prompt === ""
              ? ""
              : ` · ${card.close_prompt}`}
          </p>
          {card.service_ids.length > 0 ? (
            <p data-testid="watcher-apps-do-not-close">
              {Object.values(statuses).some(
                (status) => status !== null && status.in_use,
              )
                ? t("watcher.page.doNotClose")
                : t("watcher.page.safeToClose")}
            </p>
          ) : null}
          {card.service_ids.map((id) => {
            const status = statuses[id] ?? null;
            const error = rowErrors[id] ?? null;
            return (
              <dl key={id} data-testid={`watcher-service-${id}`}>
                <dt>{id}</dt>
                <dd>
                  {status === null
                    ? t("watcher.tab.notKnown")
                    : t(serviceStateLocaleKey(status.state))}
                  {" · "}
                  {status === null
                    ? ""
                    : status.in_use
                      ? t("watcher.page.inUse")
                      : t("watcher.page.idle")}
                  {status !== null && status.in_use ? (
                    <span data-testid={`watcher-service-${id}-hold`}>
                      {" "}
                      · {t("watcher.page.doNotClose")}
                    </span>
                  ) : null}
                </dd>
                {status !== null ? (
                  <dd data-testid={`watcher-service-${id}-usage`}>
                    {t("watcher.page.lastUsedBy")}: {status.last_agent}
                    {status.last_used !== ""
                      ? ` · ${formatScreenTime(status.last_used)}`
                      : ""}
                  </dd>
                ) : null}
                <dd>
                  <label>
                    {t("watcher.page.checkKind")}
                    <select
                      data-testid={`watcher-service-${id}-kind`}
                      value={kinds[id] ?? "HTTP"}
                      onChange={(event) => {
                        const next = event.target.value as ServiceCheckKind;
                        if (!SERVICE_CHECK_KINDS.includes(next)) {
                          return;
                        }
                        setKinds((prev) => ({ ...prev, [id]: next }));
                      }}
                    >
                      {SERVICE_CHECK_KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {kind}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    data-testid={`watcher-service-${id}-check`}
                    disabled={busy[id] === true}
                    onClick={() => {
                      void check(id);
                    }}
                  >
                    {t("watcher.page.checkService")}
                  </button>
                </dd>
                {error !== null ? (
                  <dd data-testid={`watcher-service-${id}-error`}>
                    <ErrorPanel
                      errorKey={error.errorKey}
                      code={error.code}
                      onRetry={() => {
                        void check(id);
                      }}
                    />
                  </dd>
                ) : null}
              </dl>
            );
          })}
        </>
      ) : null}
      {cardError !== null ? (
        <div data-testid="watcher-apps-error">
          <ErrorPanel
            errorKey={cardError.errorKey}
            code={cardError.code}
            onRetry={() => {
              void load();
            }}
          />
        </div>
      ) : null}
    </section>
  );
}
