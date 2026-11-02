// Clean-disconnect dialog. Confirming removes the key's store entry;
// the parent clears the provider state via onDisconnected.
// A centred modal over a backdrop (same overlay as the connect dialog);
// focus starts on Cancel. Closable via backdrop click, Escape, the X
// button, and Cancel.

import { useEffect, useRef, useState } from "react";
import { disconnectProvider, isNetworkFailure } from "./connectApi";
import { ApiError } from "../../api/errors";
import { t } from "../../locale/index";
import { APP_NAMESPACE_PREFIX } from "./types";
import { secretIdForProvider } from "./secretStore";
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

function disconnectFailure(err: unknown): string {
  if (err instanceof ApiError) {
    return t("providers.disconnect.failedCode", { code: err.code, status: String(err.status) });
  }
  if (err instanceof Error && err.message.length > 0) {
    return t("providers.disconnect.failedMessage", { message: err.message });
  }
  return t("providers.disconnect.failedGeneric");
}

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
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    setBusy(false);
    setError(null);
    return undefined;
  }, [open, secretId, provider_id]);

  // The modal opens on the safe choice: focus starts on Cancel, never
  // on the destructive confirm.
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    if (cancelRef.current !== null) {
      cancelRef.current.focus();
    }
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

  async function removeLocalReference(): Promise<void> {
    const rows = await store.list(APP_NAMESPACE_PREFIX);
    const bound = rows.find((row) => row.secret_id === secretId) ?? null;
    if (bound === null || bound.provider_id !== provider_id) {
      throw new Error(
        t("providers.disconnect.refused", { secret: secretId, provider: provider_id }),
      );
    }
    await store.remove(secretId, sessionToken);
    onDisconnected(secretId);
    onClose();
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
      // with no store call and no route call.
      if (secretId !== secretIdForProvider(provider_id)) {
        setError(t("providers.disconnect.refused", { secret: secretId, provider: provider_id }));
        return;
      }
      if (sessionToken.length === 0) {
        // Token-less runs never touch the network; the local refusal
        // below surfaces without a route call.
        await removeLocalReference();
        return;
      }
      try {
        await disconnectProvider(provider_id);
      } catch (err: unknown) {
        if (!isNetworkFailure(err)) {
          setError(disconnectFailure(err));
          return;
        }
        // No route answered (offline run): fall through to the local
        // reference flow, which keeps the saved behavior.
        await removeLocalReference();
        return;
      }
      // The route answered: the local reference is a mirror only and a
      // missing mirror entry never blocks the confirmed disconnect.
      try {
        await store.remove(secretId, sessionToken);
      } catch {
        // Mirror already gone; the server answer rules.
      }
      onDisconnected(secretId);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("providers.disconnect.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="disconnect-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "#000",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("providers.disconnect.title", { label: providerLabel })}
        style={{
          backgroundColor: "var(--agent-si-surface, #fff)",
          padding: 16,
          borderRadius: 8,
          width: "calc(100% - 32px)",
          maxWidth: 480,
          maxHeight: "calc(100vh - 64px)",
          overflowY: "auto",
        }}
      >
        <button
          type="button"
          data-variant="quiet"
          aria-label={t("providers.disconnect.close")}
          onClick={onClose}
        >
          {t("providers.disconnect.closeGlyph")}
        </button>
        <h2>{t("providers.disconnect.title", { label: providerLabel })}</h2>
        <p>{t("providers.disconnect.body", { id: secretId })}</p>
        {error !== null ? <p role="alert">{error}</p> : null}
        <button
          type="button"
          ref={cancelRef}
          data-variant="quiet"
          onClick={onClose}
        >
          {t("providers.disconnect.cancel")}
        </button>
        <button
          type="button"
          data-variant="primary"
          style={{ fontWeight: 700 }}
          disabled={busy}
          onClick={() => {
            void handleDisconnect();
          }}
        >
          {busy ? t("providers.disconnect.busy") : t("providers.disconnect.confirm")}
        </button>
      </div>
    </div>
  );
}
