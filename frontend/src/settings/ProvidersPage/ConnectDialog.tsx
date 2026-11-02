// Key-only connect dialog. The preset fills id, type and base URL;
// the user only types the key. Save is bounded and reports visibly.
// The dialog is a centred modal over a backdrop (it renders at the end
// of the Providers page, so only an overlay keeps it on screen); focus
// starts in the key field. Closable via backdrop click, Escape, the X
// button, and Cancel. The success line appears only after a real route
// round trip (plus the local mirror write): an unreachable store shows
// an honest error and the provider stays disconnected.

import { useEffect, useRef, useState } from "react";
import {
  connectCloud,
  connectLocal,
  saveKey,
} from "./connectApi";
import { ApiError } from "../../api/errors";
import { t } from "../../locale/index";
import { secretIdForProvider } from "./secretStore";
import type { SecretStorePort } from "./secretStore";
import type { ProviderPreset, SecretRef } from "./types";

export type ConnectResult = {
  kind: "success" | "error";
  text: string;
};

type ConnectDialogProps = {
  preset_id: string;
  preset: ProviderPreset | null;
  open: boolean;
  store: SecretStorePort;
  timeoutMs?: number;
  onClose: () => void;
  onConnected: (presetId: string, ref: SecretRef) => void;
};

export const CONNECT_TIMEOUT_MS = 8000;

export function saveWithTimeout(task: Promise<void>, timeoutMs: number): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(t("providers.connect.timeout", { ms: String(timeoutMs) })));
    }, timeoutMs);
    task.then(
      () => {
        clearTimeout(timer);
        resolve();
      },
      (err: unknown) => {
        clearTimeout(timer);
        reject(err instanceof Error ? err : new Error(t("providers.connect.saveFailed")));
      },
    );
  });
}

function connectFailure(err: unknown): string {
  if (err instanceof ApiError) {
    return t("providers.connect.failedCode", { code: err.code, status: String(err.status) });
  }
  if (err instanceof Error && err.message.length > 0) {
    return t("providers.connect.failedMessage", { message: err.message });
  }
  return t("providers.connect.failedGeneric");
}

export function ConnectDialog({
  preset_id,
  preset,
  open,
  store,
  timeoutMs = CONNECT_TIMEOUT_MS,
  onClose,
  onConnected,
}: ConnectDialogProps) {
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<ConnectResult | null>(null);
  const keyRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    setApiKey("");
    setResult(null);
    setSaving(false);
    return undefined;
  }, [open, preset, preset_id]);

  // L1: the key field takes focus whenever the modal opens, so the
  // keyboard lands in the single input rather than on a button.
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    if (keyRef.current !== null) {
      keyRef.current.focus();
    }
    return undefined;
  }, [open, preset, preset_id]);

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

  if (!open || preset === null) {
    return null;
  }

  const showHintWarning =
    apiKey.length > 0 && preset.keyStartsWith.length > 0 && !apiKey.startsWith(preset.keyStartsWith);

  async function handleSave(): Promise<void> {
    if (apiKey.length === 0 || saving || preset === null) {
      return;
    }
    const activePreset: ProviderPreset = preset;
    // The frozen identity is preset_id: a mismatch is refused visibly
    // with no store call.
    if (activePreset.id !== preset_id) {
      setResult({ kind: "error", text: t("providers.connect.refusedMismatch", { id: preset_id }) });
      return;
    }
    setSaving(true);
    setResult(null);
    // The key itself is never stored or logged; only this reference is saved.
    const ref: SecretRef = {
      secret_id: secretIdForProvider(preset_id),
      provider_id: preset_id,
      type: "api-key",
      scope: "providers",
      source: "providers-page",
      created_at: new Date().toISOString(),
      last_rotated_at: null,
    };
    // The typed key travels only in the key-save POST body; the local copy
    // below is dropped once the route round trip answers.
    const capturedKey = apiKey;
    try {
      if (activePreset.kind === "local") {
        await connectLocal(activePreset.baseUrl);
      } else {
        const firstModel = activePreset.models[0];
        if (firstModel === undefined) {
          setResult({ kind: "error", text: t("providers.connect.refusedNoModel", { id: preset_id }) });
          setSaving(false);
          return;
        }
        const savedRef = await saveKey(preset_id, capturedKey);
        await connectCloud({ preset_id, model: firstModel.id, key_ref: savedRef ?? ref });
      }
      // The route answered: the key leaves component state at once, and
      // the mirror write below runs only now, so "Connected" always
      // names a real save — never an unreachable store.
      setApiKey("");
      await saveWithTimeout(store.save(ref), timeoutMs);
      setResult({
        kind: "success",
        text: t("providers.connect.connected", { label: activePreset.label }),
      });
      onConnected(preset_id, ref);
    } catch (err: unknown) {
      // Any failure (route or mirror write) shows an honest error: the
      // key never reached a store, so the provider stays disconnected.
      setApiKey("");
      setResult({ kind: "error", text: connectFailure(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      data-testid="connect-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("providers.connect.title", { label: preset.label })}
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
          aria-label={t("providers.connect.close")}
          onClick={onClose}
        >
          {t("providers.connect.closeGlyph")}
        </button>
      <h2>{t("providers.connect.title", { label: preset.label })}</h2>
      <dl>
        <div>
          <dt>{t("providers.connect.providerId")}</dt>
          <dd>{preset.id}</dd>
        </div>
        <div>
          <dt>{t("providers.connect.kind")}</dt>
          <dd>{preset.kind}</dd>
        </div>
        <div>
          <dt>{t("providers.connect.baseUrl")}</dt>
          <dd>{preset.baseUrl}</dd>
        </div>
      </dl>
      <label>
        {t("providers.connect.apiKey")}
        <input
          ref={keyRef}
          type="password"
          aria-label={t("providers.connect.apiKey")}
          value={apiKey}
          autoComplete="off"
          onChange={(event) => setApiKey(event.target.value)}
        />
      </label>
      <p>{t("providers.connect.keyFormat", { hint: preset.keyHint })}</p>
      {showHintWarning ? <p>{t("providers.connect.hintMismatch")}</p> : null}
      {result !== null ? <p role="status">{result.text}</p> : null}
      <button type="button" data-variant="quiet" onClick={onClose}>
        {t("providers.connect.cancel")}
      </button>
      <button
        type="button"
        data-variant="primary"
        style={{ fontWeight: 700 }}
        disabled={apiKey.length === 0 || saving}
        onClick={() => {
          void handleSave();
        }}
      >
        {saving ? t("providers.connect.saving") : t("providers.connect.save")}
      </button>
      </div>
    </div>
  );
}
