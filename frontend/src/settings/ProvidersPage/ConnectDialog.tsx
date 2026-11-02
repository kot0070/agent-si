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
import { listProviderModels, modelPriceText } from "./modelsApi";
import type { ProviderModelRow } from "./modelsApi";
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
  // Step-2 additions (all optional; omitting them keeps the old key-only
  // contract): Manage models opens at step 2 with the current ticks, Done
  // reports the ticked ids through onModelsDone before closing.
  initialStep?: 1 | 2;
  initialTicked?: string[];
  onModelsDone?: (presetId: string, modelIds: string[]) => void;
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
  initialStep,
  initialTicked,
  onModelsDone,
}: ConnectDialogProps) {
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<ConnectResult | null>(null);
  // Step 2: the model list inside the same dialog (Connected line, loading
  // state, tickable rows, Done closes). The key is already cleared.
  const [step, setStep] = useState<1 | 2>(1);
  const [modelRows, setModelRows] = useState<ProviderModelRow[]>([]);
  const [modelSource, setModelSource] = useState<"provider" | "catalog" | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [ticked, setTicked] = useState<string[]>([]);
  const [modelQuery, setModelQuery] = useState("");
  const keyRef = useRef<HTMLInputElement | null>(null);
  const initialTickedRef = useRef<string[] | undefined>(initialTicked);
  initialTickedRef.current = initialTicked;

  function closeAndClear(): void {
    // The key leaves component state on every close, mid-save or not.
    setApiKey("");
    onClose();
  }

  async function loadModels(activePreset: ProviderPreset): Promise<void> {
    setModelsLoading(true);
    try {
      const outcome = await listProviderModels(activePreset.id, activePreset.models);
      setModelRows(outcome.rows);
      setModelSource(outcome.source);
      const known = new Set(outcome.rows.map((row) => row.id));
      const fromRoute = initialTickedRef.current;
      if (outcome.servedEnabled !== null) {
        // The server's enabled list is the routing truth: it wins over the
        // passed-in ticks whenever the route names it.
        setTicked(outcome.servedEnabled.filter((id) => known.has(id)));
      } else if (fromRoute !== undefined) {
        // Manage models without a served truth: keep the current ticks,
        // drop ids no longer listed.
        setTicked(fromRoute.filter((id) => known.has(id)));
      } else {
        // Fresh connect: only the default (connect) model ticked, never all.
        const first = activePreset.models[0];
        setTicked(first === undefined ? [] : [first.id].filter((id) => known.has(id)));
      }
    } finally {
      setModelsLoading(false);
    }
  }

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const activePreset: ProviderPreset | null = preset;
    setApiKey("");
    setResult(null);
    setSaving(false);
    setModelQuery("");
    setModelSource(null);
    const first = activePreset?.models[0];
    const fallbackTicked = first === undefined ? [] : [first.id];
    setTicked(initialTicked ?? fallbackTicked);
    if (initialStep === 2 && activePreset !== null) {
      setStep(2);
      setModelRows([]);
      void loadModels(activePreset);
    } else {
      setStep(1);
      setModelRows([]);
    }
    return undefined;
  }, [open, preset, preset_id, initialStep]);

  // L1: the key field takes focus whenever the modal opens on step 1, so
  // the keyboard lands in the single input rather than on a button.
  useEffect(() => {
    if (!open || step !== 1) {
      return undefined;
    }
    if (keyRef.current !== null) {
      keyRef.current.focus();
    }
    return undefined;
  }, [open, preset, preset_id, step]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    // X, Esc and the backdrop always close, even during a pending save:
    // the key leaves state with the close and the save settles unseen.
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setApiKey("");
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
      // Step 1 done: the same dialog moves to step 2 (Connected line plus
      // the tickable model list). Done closes; X/Esc/backdrop close any time.
      setStep(2);
      setModelRows([]);
      await loadModels(activePreset);
    } catch (err: unknown) {
      // Any failure (route or mirror write) shows an honest error: the
      // key never reached a store, so the provider stays disconnected.
      setApiKey("");
      setResult({ kind: "error", text: connectFailure(err) });
    } finally {
      setSaving(false);
    }
  }

  const needle = modelQuery.trim().toLowerCase();
  const shownRows = needle.length === 0
    ? modelRows
    : modelRows.filter(
        (row) =>
          row.label.toLowerCase().includes(needle) ||
          row.id.toLowerCase().includes(needle),
      );

  function toggleTicked(modelId: string): void {
    setTicked((prev) =>
      prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId],
    );
  }

  function handleDone(): void {
    // Ticks commit to the page (routing truth comes from a route once the
    // backend names one; until then the page feeds Auto and role pickers).
    onModelsDone?.(preset_id, ticked);
    closeAndClear();
  }

  return (
    <div
      data-testid="connect-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          closeAndClear();
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
          onClick={closeAndClear}
        >
          {t("providers.connect.closeGlyph")}
        </button>
      <h2>{t("providers.connect.title", { label: preset.label })}</h2>
      <p data-variant="quiet">
        <span>{preset.id}</span>
        {" · "}
        <span>{preset.kind}</span>
        {" · "}
        <span>{preset.baseUrl}</span>
      </p>
      {step === 1 ? (
      <>
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
      <button type="button" data-variant="quiet" onClick={closeAndClear}>
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
      </>
      ) : (
      <>
      <p role="status" data-variant="quiet">
        {t("providers.connect.connected", { label: preset.label })}
      </p>
      {modelsLoading ? (
        <p role="status">Loading models...</p>
      ) : (
      <>
      <label>
        Filter models
        <input
          type="search"
          aria-label="Filter models"
          value={modelQuery}
          onChange={(event) => setModelQuery(event.target.value)}
        />
      </label>
      {modelSource === "catalog" ? (
        <p data-variant="quiet">showing the known list</p>
      ) : null}
      <div
        data-testid="connect-model-list"
        style={{ maxHeight: 240, overflowY: "auto" }}
      >
        <ul>
          {shownRows.map((row) => (
            <li key={row.id} data-testid="connect-model-row">
              <input
                type="checkbox"
                aria-label={`${preset.label} ${row.label}`}
                checked={ticked.includes(row.id)}
                onChange={() => toggleTicked(row.id)}
              />{" "}
              <span>{row.label}</span>{" "}
              <small data-testid={`connect-model-id-${row.id}`}>{row.id}</small>{" "}
              <span data-testid={`connect-model-price-${row.id}`}>
                {modelPriceText(row.kb, row.price)}
              </span>
              {row.kbKnown === false ? (
                <span data-testid={`connect-model-kb-${row.id}`}>
                  {" "}not in capability base
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      </>
      )}
      <button type="button" data-variant="quiet" onClick={closeAndClear}>
        {t("providers.connect.cancel")}
      </button>
      <button
        type="button"
        data-variant="primary"
        style={{ fontWeight: 700 }}
        onClick={handleDone}
      >
        Done
      </button>
      </>
      )}
      </div>
    </div>
  );
}
