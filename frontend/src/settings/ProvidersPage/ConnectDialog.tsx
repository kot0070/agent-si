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
  checkKey,
  connectCloud,
  connectLocal,
  probeLocalModels,
  saveKey,
} from "./connectApi";
import { ApiError } from "../../api/errors";
import { t } from "../../locale/index";
import { secretIdForProvider } from "./secretStore";
import { listProviderModels, modelPriceText, refreshProviderModels, saveEnabledModels } from "./modelsApi";
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
    // FXR2E wrong key: the refused key and the unreachable provider
    // read as fixed plain strings, never a machine code. Anything
    // else shows the served plain text when the route sent one.
    const code = String(err.code);
    if (err.status === 401 || err.status === 403
      || code === "PROVIDER_KEY_REFUSED") {
      return t("providers.connect.refusedKey");
    }
    if (err.status === 0 || err.status === 503
      || code === "EVIDENCE_PROBE_NETWORK") {
      // FXSPEED S3: the slow/unreachable sentence is the locale text
      // (the key is kept, Connect again retries); refused keys never
      // reach this branch (401/403 above).
      return t("providers.connect.unreachable");
    }
    // FXSMALL item 6: a conflicting re-connect (same id, different base
    // URL) refuses with a code the dialog maps to one plain sentence;
    // the raw backend text never reaches the user in either locale.
    if (code === "PROVIDER_CONFLICT") {
      return t("providers.connect.conflict");
    }
    if (typeof err.details?.message === "string"
      && err.details.message.length > 0) {
      return t("providers.connect.failedMessage",
        { message: err.details.message });
    }
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
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState(false);
  const [result, setResult] = useState<ConnectResult | null>(null);
  // Step 2: the model list inside the same dialog (Connected line, loading
  // state, tickable rows, Done closes). The key is already cleared.
  const [step, setStep] = useState<1 | 2>(1);
  const [modelRows, setModelRows] = useState<ProviderModelRow[]>([]);
  const [modelSource, setModelSource] = useState<"provider" | "catalog" | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [ticked, setTicked] = useState<string[]>([]);
  const [modelQuery, setModelQuery] = useState("");
  // Y2: Done with nothing ticked warns instead of closing silently.
  const [doneNote, setDoneNote] = useState<string | null>(null);
  // Quiet Refresh state: a failed refresh keeps the last list plus one
  // calm line; Done PUT state: a failed save keeps the dialog open.
  const [refreshNote, setRefreshNote] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
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
      } else if (fromRoute !== undefined && fromRoute.length > 0) {
        // Manage models without a served truth: keep the current ticks,
        // drop ids no longer listed. An empty list means no preference,
        // so fall through to the recommended text model below.
        setTicked(fromRoute.filter((id) => known.has(id)));
      } else {
        // Fresh connect, or Manage opened with nothing ticked: pre-tick
        // the recommended text model (the connect id), never all and
        // never an empty selection.
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
    setChecking(false);
    setChecked(false);
    setModelQuery("");
    setModelSource(null);
    setRefreshNote(null);
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

  // FXFIRST: local presets need no key — Check and Save stay enabled
  // with an empty key and probe the local URL instead (cloud rows keep
  // the key-first two-step and its check-first hint).
  const isLocal = preset.kind === "local";

  const showHintWarning =
    apiKey.length > 0 && preset.keyStartsWith.length > 0 && !apiKey.startsWith(preset.keyStartsWith);

  async function handleCheck(): Promise<void> {
    // Step 1 of the two-step dialog: paste + Check, then Save. The check
    // hits the read-only route (same live preflight, never stores), so a
    // wrong key reports the plain reason and leaves every store alone.
    // FXFIRST: local presets need no key, so Check stays enabled with an
    // empty key and really probes the local URL instead of self-approving.
    if (checking || saving || preset === null) {
      return;
    }
    const activePreset: ProviderPreset = preset;
    if (activePreset.id !== preset_id) {
      setResult({ kind: "error", text: t("providers.connect.refusedMismatch", { id: preset_id }) });
      return;
    }
    if (activePreset.kind === "local") {
      setChecking(true);
      setResult(null);
      try {
        const count = await probeLocalModels(activePreset.baseUrl);
        if (count === null) {
          setChecked(false);
          setResult({
            kind: "error",
            text: t("providers.connect.localNotRunning", { label: activePreset.label }),
          });
        } else {
          setChecked(true);
          setResult({
            kind: "success",
            text: t("providers.connect.localFound", { count: String(count) }),
          });
        }
      } catch (err: unknown) {
        setChecked(false);
        setResult({ kind: "error", text: connectFailure(err) });
      } finally {
        setChecking(false);
      }
      return;
    }
    if (apiKey.length === 0) {
      return;
    }
    setChecking(true);
    setResult(null);
    try {
      await checkKey(preset_id, apiKey);
      setChecked(true);
      setResult({ kind: "success", text: t("providers.connect.checked") });
    } catch (err: unknown) {
      setChecked(false);
      setResult({ kind: "error", text: connectFailure(err) });
    } finally {
      setChecking(false);
    }
  }

  async function handleSave(): Promise<void> {
    if (saving || preset === null) {
      return;
    }
    // Two-step: Save runs only after a successful Check for cloud
    // presets (local presets need no key check, so an empty key saves).
    // The save itself re-checks before storing, so a key swapped after
    // Check still cannot store a refused value.
    if (preset.kind !== "local" && (apiKey.length === 0 || !checked)) {
      setResult({ kind: "error", text: t("providers.connect.checkFirst") });
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
      // H3: never a bare generic — always the reason plus what to do.
      setApiKey("");
      // FXSPEED S3: a slow/unreachable provider keeps the saved key, so
      // the result names only what to do (Connect again) without the
      // re-paste hint, which is reserved for refused keys.
      const faultCode = err instanceof ApiError ? String(err.code) : "";
      const base = connectFailure(err);
      const hint = faultCode === "EVIDENCE_PROBE_NETWORK"
        ? ""
        : ` ${t("providers.connect.retryHint", { label: activePreset.label })}`;
      setResult({ kind: "error", text: `${base}${hint}` });
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
    setDoneNote(null);
    setTicked((prev) =>
      prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId],
    );
  }

  function handleDone(): void {
    // Done PUTs the ticked ids and closes at once (the dialog always
    // closed synchronously on Done). The server's enabled list is the
    // routing truth: a saved list that differs is reconciled back onto
    // the page, and a failed save re-reads the served ticks so the page
    // never shows ticks the server refused.
    // Y2: Done with nothing ticked warns and stays open; a silent
    // close would drop the provider to zero usable models.
    if (preset === null) {
      return;
    }
    const activePreset: ProviderPreset = preset;
    const ids = ticked;
    if (ids.length === 0) {
      setDoneNote(t("providers.connect.needOneModel"));
      return;
    }
    setDoneNote(null);
    onModelsDone?.(preset_id, ids);
    closeAndClear();
    void saveEnabledModels(activePreset.id, ids).then(
      (saved) => {
        if (JSON.stringify(saved) !== JSON.stringify(ids)) {
          onModelsDone?.(preset_id, saved);
        }
      },
      () => {
        void listProviderModels(activePreset.id, activePreset.models).then(
          (outcome) => {
            if (outcome.servedEnabled !== null) {
              onModelsDone?.(preset_id, outcome.servedEnabled);
            }
          },
          () => undefined,
        );
      },
    );
  }

  function handleRefresh(): void {
    // Quiet Refresh: re-read the live list; any failure keeps the last
    // list plus one calm line.
    if (refreshing || preset === null || step !== 2) {
      return;
    }
    const activePreset: ProviderPreset = preset;
    setRefreshing(true);
    setRefreshNote(null);
    refreshProviderModels(activePreset.id, activePreset.models).then(
      (outcome) => {
        setRefreshing(false);
        setModelRows(outcome.rows);
        setModelSource(outcome.source);
        const known = new Set(outcome.rows.map((row) => row.id));
        if (outcome.servedEnabled !== null) {
          setTicked(outcome.servedEnabled.filter((id) => known.has(id)));
        }
      },
      () => {
        setRefreshing(false);
        setRefreshNote(t("providers.connect.refreshFailed"));
      },
    );
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
        backgroundColor: "rgba(0, 0, 0, 0.5)",
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
          onChange={(event) => { setApiKey(event.target.value); setChecked(false); }}
        />
      </label>
      <p>{t("providers.connect.keyFormat", { hint: preset.keyHint })}</p>
      <p data-variant="quiet">{t("providers.connect.storeNote")}</p>
      {showHintWarning ? <p>{t("providers.connect.hintMismatch")}</p> : null}
      {result !== null ? <p role="status">{result.text}</p> : null}
      {/* U7: Cancel + Save share one spaced action row. */}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <button type="button" data-variant="quiet" onClick={closeAndClear}>
        {t("providers.connect.cancel")}
      </button>
      <button
        type="button"
        data-variant="quiet"
        disabled={(!isLocal && apiKey.length === 0) || checking || saving}
        onClick={() => {
          void handleCheck();
        }}
      >
        {checking ? t("providers.connect.checking") : t("providers.connect.check")}
      </button>
      <button
        type="button"
        data-variant="primary"
        style={{ fontWeight: 700 }}
        disabled={saving || (!isLocal && (apiKey.length === 0 || !checked))}
        onClick={() => {
          void handleSave();
        }}
      >
        {saving ? t("providers.connect.saving") : t("providers.connect.save")}
      </button>
      </div>
      {/* FXC2 advisor: a disabled Save needs its reason on screen. */}
      {preset.kind !== "local" && !checked && apiKey.length > 0 ? (
        <p data-testid="connect-check-first" data-variant="quiet">
          <small>{t("providers.connect.checkFirst")}</small>
        </p>
      ) : null}
      </>
      ) : (
      <>
      <p role="status" data-variant="quiet">
        {t("providers.connect.connected", { label: preset.label })}
      </p>
      {modelsLoading ? (
        <p role="status">{t("providers.connect.loadingModels")}</p>
      ) : (
      <>
      <div>
      <button
        type="button"
        data-variant="quiet"
        disabled={refreshing}
        onClick={handleRefresh}
      >
        {refreshing ? t("providers.connect.refreshingModels") : t("providers.connect.refreshModels")}
      </button>
      {refreshNote !== null ? <p data-variant="quiet">{refreshNote}</p> : null}
      </div>
      <label>
        {t("providers.connect.filterModels")}
        <input
          type="search"
          aria-label={t("providers.connect.filterModels")}
          value={modelQuery}
          onChange={(event) => setModelQuery(event.target.value)}
        />
      </label>
      {modelSource === "catalog" && shownRows.length > 0 ? (
        <p data-variant="quiet">{t("providers.connect.knownListNote")}</p>
      ) : null}
      {/* R2: a local preset with no served rows names that plainly
          instead of an empty known list. */}
      {modelSource === "catalog" && shownRows.length === 0 && preset.kind === "local" ? (
        <p data-variant="quiet">
          {t("providers.connect.localNotRunning", { label: preset.label })}
        </p>
      ) : null}
      {/* J10: one header line names the unknown models; the per-row
          chips stay, but the repetition reads once up front. */}
      {shownRows.some((row) => row.kbKnown !== true) ? (
        <p data-testid="connect-models-unknown-note" data-variant="quiet">
          {t("providers.connect.unknownModelsNote")}
        </p>
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
                aria-label={row.id}
                title={row.id}
                checked={ticked.includes(row.id)}
                onChange={() => toggleTicked(row.id)}
              />{" "}
              <>{row.label === row.id ? null : (<span>{row.label}{" "}</span>)}</>
              <small data-testid={`connect-model-id-${row.id}`} title={row.id}>{row.id}</small>{" "}
              <span data-testid={`connect-model-price-${row.id}`} data-variant="quiet">
                {modelPriceText(row.kb, row.price)}
              </span>
              {" · "}
              <span data-testid={`connect-model-kb-${row.id}`} data-variant="quiet">
                {row.kbKnown === false
                  ? t("providers.connect.kbOut")
                  : row.kbKnown === true
                    ? t("providers.connect.kbIn")
                    : t("providers.connect.kbUnknown")}
              </span>
            </li>
          ))}
        </ul>
      </div>
      </>
      )}
      {/* U7: Cancel + Done share one spaced action row. */}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <button type="button" data-variant="quiet" onClick={closeAndClear}>
        {t("providers.connect.cancel")}
      </button>
      <button
        type="button"
        data-variant="primary"
        style={{ fontWeight: 700 }}
        onClick={handleDone}
      >
        {t("providers.connect.done")}
      </button>
      </div>
      {doneNote !== null ? (
        <p data-testid="connect-done-note" role="alert">
          {doneNote}
        </p>
      ) : null}
      </>
      )}
      </div>
    </div>
  );
}
