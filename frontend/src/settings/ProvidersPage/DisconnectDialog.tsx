// Clean-disconnect dialog. Confirming removes the key's store entry;
// the parent clears the provider state via onDisconnected.
// Closable via Escape, the X button, and Cancel.

import { useEffect, useState } from "react";
import { APP_NAMESPACE_PREFIX } from "./types";
import type { SecretStorePort } from "./secretStore";

type DisconnectDialogProps = {
  provider_id: string;
  providerLabel: string;
  secretId: string;
  open: boolean;
  store: SecretStorePort;
  sessionToken: string;
  onClose: () => void;
  onDisconnected: (secretId: string) => void;
};

export function DisconnectDialog({
  provider_id,
  providerLabel,
  secretId,
  open,
  store,
  sessionToken,
  onClose,
  onDisconnected,
}: DisconnectDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    setBusy(false);
    setError(null);
    return undefined;
  }, [open, secretId, provider_id]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  async function handleDisconnect(): Promise<void> {
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // The frozen identity is provider_id: the remove runs only for a
      // secret bound to that provider; a mismatch is refused visibly
      // with no store call.
      const rows = await store.list(APP_NAMESPACE_PREFIX);
      const bound = rows.find((row) => row.secret_id === secretId) ?? null;
      if (bound === null || bound.provider_id !== provider_id) {
        setError(`Refused: secret ${secretId} is not bound to provider ${provider_id}.`);
        return;
      }
      await store.remove(secretId, sessionToken);
      onDisconnected(secretId);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Disconnect failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label={`Disconnect ${providerLabel}`}>
      <button type="button" aria-label="Close" onClick={onClose}>
        X
      </button>
      <h2>Disconnect {providerLabel}</h2>
      <p>This removes the saved key reference {secretId}.</p>
      {error !== null ? <p role="alert">{error}</p> : null}
      <button type="button" onClick={onClose}>
        Cancel
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          void handleDisconnect();
        }}
      >
        {busy ? "Disconnecting..." : "Disconnect"}
      </button>
    </div>
  );
}
