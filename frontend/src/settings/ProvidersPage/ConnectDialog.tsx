// Key-only connect dialog. The preset fills id, type and base URL;
// the user only types the key. Save is bounded and reports visibly.
// Closable via Escape, the X button, and Cancel.

import { useEffect, useState } from "react";
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
      reject(new Error(`Save timed out after ${timeoutMs} ms.`));
    }, timeoutMs);
    task.then(
      () => {
        clearTimeout(timer);
        resolve();
      },
      (err: unknown) => {
        clearTimeout(timer);
        reject(err instanceof Error ? err : new Error("Save failed."));
      },
    );
  });
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

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    setApiKey("");
    setResult(null);
    setSaving(false);
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
      setResult({ kind: "error", text: `Refused: preset mismatch for ${preset_id}.` });
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
    try {
      await saveWithTimeout(store.save(ref), timeoutMs);
      setResult({ kind: "success", text: `Connected ${activePreset.label}. Reference saved.` });
      onConnected(preset_id, ref);
    } catch (err: unknown) {
      setResult({ kind: "error", text: err instanceof Error ? err.message : "Save failed." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label={`Connect ${preset.label}`}>
      <button type="button" aria-label="Close" onClick={onClose}>
        X
      </button>
      <h2>Connect {preset.label}</h2>
      <dl>
        <div>
          <dt>Provider ID</dt>
          <dd>{preset.id}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{preset.kind}</dd>
        </div>
        <div>
          <dt>Base URL</dt>
          <dd>{preset.baseUrl}</dd>
        </div>
      </dl>
      <label>
        API key
        <input
          type="password"
          aria-label="API key"
          value={apiKey}
          autoComplete="off"
          onChange={(event) => setApiKey(event.target.value)}
        />
      </label>
      <p>Key format: {preset.keyHint}</p>
      {showHintWarning ? <p>This key does not match the expected format.</p> : null}
      {result !== null ? <p role="status">{result.text}</p> : null}
      <button type="button" onClick={onClose}>
        Cancel
      </button>
      <button
        type="button"
        disabled={apiKey.length === 0 || saving}
        onClick={() => {
          void handleSave();
        }}
      >
        {saving ? "Saving..." : "Save"}
      </button>
    </div>
  );
}
