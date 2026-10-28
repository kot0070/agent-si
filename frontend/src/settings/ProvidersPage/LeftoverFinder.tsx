// Leftover-key finder. Lists entries under the app namespace prefix only,
// showing names and dates only (references carry no key material).
// Deletion is user-click only, needs a per-entry confirm plus a session
// token, never touches live-provider-linked entries, and is audit-logged
// by entry name only.

import { useEffect, useState } from "react";
import { APP_NAMESPACE_PREFIX } from "./types";
import type { SecretStorePort } from "./secretStore";
import type { SecretRef } from "./types";

type LeftoverFinderProps = {
  store: SecretStorePort;
  sessionToken: string;
  linkedSecretIds: string[];
  refreshKey?: number;
};

export function LeftoverFinder({
  store,
  sessionToken,
  linkedSecretIds,
  refreshKey = 0,
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
          setError(err instanceof Error ? err.message : "Could not list entries.");
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
      await store.remove(entry.secret_id, sessionToken);
      setArmedId(null);
      setNotice(`Deleted ${entry.secret_id}.`);
      setEntries((prev) => prev.filter((row) => row.secret_id !== entry.secret_id));
    } catch (err: unknown) {
      setNotice(null);
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error !== null ? <p role="alert">{error}</p> : null}
      {notice !== null ? <p role="status">{notice}</p> : null}
      {entries.length === 0 ? (
        <p>No leftover keys.</p>
      ) : (
        <ul>
          {entries.map((entry) => {
            const linked = linkedSecretIds.includes(entry.secret_id);
            const armed = armedId === entry.secret_id;
            return (
              <li key={entry.secret_id} data-testid="leftover-entry">
                <span>{entry.secret_id}</span>
                <span>Created: {entry.created_at}</span>
                {entry.last_rotated_at !== null ? (
                  <span>Rotated: {entry.last_rotated_at}</span>
                ) : null}
                {linked ? (
                  <span title="In use by a live provider">In use</span>
                ) : (
                  <span>
                    <button
                      type="button"
                      aria-label={`Delete ${entry.secret_id}`}
                      disabled={busy}
                      onClick={() => {
                        void handleDelete(entry);
                      }}
                    >
                      {armed ? "Confirm delete" : "Delete"}
                    </button>
                    {armed ? (
                      <button type="button" onClick={() => setArmedId(null)}>
                        Cancel
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
