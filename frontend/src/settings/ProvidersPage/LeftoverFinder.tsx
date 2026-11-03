// Leftover-key finder. Lists entries under the app namespace prefix only,
// showing names and dates only (references carry no key material).
// Deletion is user-click only, needs a per-entry confirm plus a session
// token, never touches live-provider-linked entries, and is audit-logged
// by entry name only. Pass deleteEntry to delete through the real route
// instead of the bound store.

import { useEffect, useState } from "react";
import { APP_NAMESPACE_PREFIX } from "./types";
import { t } from "../../locale/index";
import type { SecretStorePort } from "./secretStore";
import type { SecretRef } from "./types";

type LeftoverFinderProps = {
  store: SecretStorePort;
  sessionToken: string;
  linkedSecretIds: string[];
  refreshKey?: number;
  deleteEntry?: (entry: SecretRef) => Promise<void>;
};

export function LeftoverFinder({
  store,
  sessionToken,
  linkedSecretIds,
  refreshKey = 0,
  deleteEntry,
}: LeftoverFinderProps) {
  const [entries, setEntries] = useState<SecretRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [armedId, setArmedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    store.list(APP_NAMESPACE_PREFIX).then(
      (rows) => {
        if (!cancelled) {
          setEntries(rows);
          setError(null);
        }
      },
      (err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("providers.leftover.listFailed"));
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [store, refreshKey]);

  async function handleDelete(entry: SecretRef): Promise<void> {
    if (linkedSecretIds.includes(entry.secret_id)) {
      return;
    }
    if (armedId !== entry.secret_id) {
      setArmedId(entry.secret_id);
      setNotice(null);
      return;
    }
    setBusy(true);
    try {
      if (deleteEntry) {
        await deleteEntry(entry);
      } else {
        await store.remove(entry.secret_id, sessionToken);
      }
      setArmedId(null);
      setNotice(t("providers.leftover.deleted", { id: entry.secret_id }));
      setEntries((prev) => prev.filter((row) => row.secret_id !== entry.secret_id));
    } catch (err: unknown) {
      setNotice(null);
      setError(err instanceof Error ? err.message : t("providers.leftover.deleteFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error !== null ? <p role="alert">{error}</p> : null}
      {notice !== null ? <p role="status">{notice}</p> : null}
      {entries.length === 0 ? (
        <p>{t("providers.leftover.empty")}</p>
      ) : (
        <ul>
          {entries.map((entry) => {
            const linked = linkedSecretIds.includes(entry.secret_id);
            const armed = armedId === entry.secret_id;
            return (
              <li key={entry.secret_id} data-testid="leftover-entry">
                <span>{entry.secret_id}</span>
                <span>{t("providers.leftover.created", { date: entry.created_at })}</span>
                {entry.last_rotated_at !== null ? (
                  <span>{t("providers.leftover.rotated", { date: entry.last_rotated_at })}</span>
                ) : null}
                {linked ? (
                  <span title={t("providers.leftover.inUseTitle")}>{t("providers.leftover.inUse")}</span>
                ) : (
                  {/* FXBTN: one spaced action row; cancel reads quiet. */}
                  <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                    <button
                      type="button"
                      aria-label={t("providers.leftover.deleteAria", { id: entry.secret_id })}
                      disabled={busy}
                      onClick={() => {
                        void handleDelete(entry);
                      }}
                    >
                      {armed ? t("providers.leftover.confirmDelete") : t("providers.leftover.delete")}
                    </button>
                    {armed ? (
                      <button type="button" data-variant="quiet" onClick={() => setArmedId(null)}>
                        {t("providers.leftover.cancel")}
                      </button>
                    ) : null}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
