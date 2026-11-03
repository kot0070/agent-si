// K07C LocalBench settings sub-lane: benchmark tab with the
// path -> scan -> level -> run flow. Duration and PC-load warnings come
// from the M3 estimate accepted for the run; per-model results render from
// the M3 result rows; the per-change decision record logs each finished
// run. Every visible string resolves through the locale; record data
// arrives only through LocalBenchClient. The tab persists its scan result
// and decision record in window.localStorage (see STORED_*_KEY) so the
// Local AI view renders the stored config without re-running the flow.

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { formatNumber, t } from "../locale/index";
import type { LocalBenchClient } from "./LocalBenchClient";
import { listConnectedProviders } from "./ProvidersPage/connectApi";
import { getProviderCatalog } from "./ProvidersPage/catalog";
import {
  BENCHMARK_LEVELS,
  DURATION_WARNING_S,
  EVIDENCE_LOCALE_KEYS,
  LEVEL_LOCALE_KEYS,
  LEVEL_PC_LOAD,
  estimateSeconds,
  kindToTier,
} from "./LocalBenchTypes";
import type {
  BenchmarkLevel,
  EvidenceTier,
  LocalBenchDecisionRecord,
  LocalBenchHardwareProfile,
  LocalBenchModel,
  LocalBenchResultRow,
  LocalBenchRunAccepted,
} from "./LocalBenchTypes";

export interface LocalBenchTabProps {
  client: LocalBenchClient;
}

// localStorage keys for the stored local-AI config (same namespaced style
// as the accepted-risk key in settings/index.ts). Values are written only
// by the bench flow below and validated on every read.
const STORED_SCAN_KEY = "agentsi.localbench.scan";
const STORED_DECISIONS_KEY = "agentsi.localbench.decisions";

export interface StoredLocalBench {
  path: string | null;
  models: Array<LocalBenchModel>;
  decisions: Array<LocalBenchDecisionRecord>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function isStoredTier(value: unknown): value is EvidenceTier {
  return typeof value === "string" && value in EVIDENCE_LOCALE_KEYS;
}

function isStoredLevel(value: unknown): value is BenchmarkLevel {
  return typeof value === "string" && value in LEVEL_LOCALE_KEYS;
}

function readStoredModels(value: unknown): Array<LocalBenchModel> {
  if (!Array.isArray(value)) {
    return [];
  }
  const models: Array<LocalBenchModel> = [];
  for (const entry of value) {
    const fields = asRecord(entry);
    if (fields === null) {
      continue;
    }
    const { model_id: modelId, display_name: displayName, evidence } = fields;
    if (
      typeof modelId === "string" &&
      modelId.length > 0 &&
      typeof displayName === "string" &&
      isStoredTier(evidence)
    ) {
      models.push({
        model_id: modelId,
        display_name: displayName,
        evidence,
      });
    }
  }
  return models;
}

function readStoredDecisions(
  value: unknown,
): Array<LocalBenchDecisionRecord> {
  if (!Array.isArray(value)) {
    return [];
  }
  const records: Array<LocalBenchDecisionRecord> = [];
  for (const entry of value) {
    const fields = asRecord(entry);
    if (fields === null) {
      continue;
    }
    const {
      decision_id: decisionId,
      change,
      run_id: runId,
      model_id: modelId,
      level,
      evidence,
      duration_s: durationS,
      recorded_at: recordedAt,
    } = fields;
    if (
      typeof decisionId === "string" &&
      decisionId.length > 0 &&
      change === "run" &&
      typeof runId === "string" &&
      runId.length > 0 &&
      typeof modelId === "string" &&
      modelId.length > 0 &&
      isStoredLevel(level) &&
      isStoredTier(evidence) &&
      typeof durationS === "number" &&
      Number.isFinite(durationS) &&
      durationS >= 0 &&
      typeof recordedAt === "string" &&
      recordedAt.length > 0
    ) {
      records.push({
        decision_id: decisionId,
        change: "run",
        run_id: runId,
        model_id: modelId,
        level,
        evidence,
        duration_s: durationS,
        recorded_at: recordedAt,
      });
    }
  }
  return records;
}

// Reads the stored local-AI config written by the bench flow. Every field
// is validated; corrupt or missing entries fall back to empty state, so a
// bad stored value never crashes a view.
export function readStoredLocalBench(): StoredLocalBench {
  const empty: StoredLocalBench = { path: null, models: [], decisions: [] };
  let scan: unknown = null;
  let decisions: unknown = null;
  try {
    scan = JSON.parse(
      window.localStorage.getItem(STORED_SCAN_KEY) ?? "null",
    );
    decisions = JSON.parse(
      window.localStorage.getItem(STORED_DECISIONS_KEY) ?? "null",
    );
  } catch {
    return empty;
  }
  const scanRecord = asRecord(scan);
  const path = scanRecord?.path;
  return {
    path: typeof path === "string" && path.length > 0 ? path : null,
    models: readStoredModels(scanRecord?.models),
    decisions: readStoredDecisions(decisions),
  };
}

function storeScanState(path: string, models: Array<LocalBenchModel>): void {
  try {
    window.localStorage.setItem(
      STORED_SCAN_KEY,
      JSON.stringify({ path, models }),
    );
  } catch {
    // Storage unavailable: the Local AI view shows its empty state.
  }
}

function storeDecisionRecords(
  decisions: Array<LocalBenchDecisionRecord>,
): void {
  try {
    window.localStorage.setItem(
      STORED_DECISIONS_KEY,
      JSON.stringify(decisions),
    );
  } catch {
    // Storage unavailable: the Local AI view shows its empty state.
  }
}

// Per-change decision record rendering shared by the bench tab and the
// Local AI view: one block, no forked copy.
export function LocalBenchDecisionList(props: {
  decisions: Array<LocalBenchDecisionRecord>;
}): ReactElement {
  const { decisions } = props;
  return (
    <div>
      <h3>{t("settings.localbench.decisionTitle")}</h3>
      {decisions.length === 0 ? (
        <p>{t("settings.localbench.decisionEmpty")}</p>
      ) : (
        <ul data-testid="localbench-decisions">
          {decisions.map((record) => (
            <li
              key={record.decision_id}
              data-testid={`localbench-decision-${record.decision_id}`}
            >
              {t("settings.localbench.decisionLine", {
                model: record.model_id,
                level: t(LEVEL_LOCALE_KEYS[record.level]),
                evidence: t(EVIDENCE_LOCALE_KEYS[record.evidence]),
                seconds: formatNumber(record.duration_s),
                at: record.recorded_at,
              })}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type ScanState =
  | { status: "idle" }
  | { status: "scanning" }
  | { status: "ready"; path: string; models: Array<LocalBenchModel> }
  | { status: "error" };

type RunState =
  | { status: "idle" }
  | { status: "running" }
  | {
      status: "ready";
      accepted: LocalBenchRunAccepted;
      rows: Array<LocalBenchResultRow>;
    }
  | { status: "error" };

function hardwareSummary(hardware: LocalBenchHardwareProfile): string {
  const ram = `${hardware.ram_mb} MB`;
  if (hardware.cpu_only || hardware.gpu_model === null) {
    return `${hardware.gpu_vendor} · ${ram}`;
  }
  return `${hardware.gpu_vendor} ${hardware.gpu_model} · ${ram}`;
}

export function LocalBenchTab(props: LocalBenchTabProps): ReactElement {
  const { client } = props;
  const [path, setPath] = useState("");
  // R5: scan source — a folder path or a connected local runtime (no
  // folder needed). "folder" is the default; runtime ids come from
  // the served connected list.
  const [source, setSource] = useState<string>("folder");
  const [runtimes, setRuntimes] = useState<
    Array<{ id: string; label: string; endpoint: string }> | null
  >(null);
  const [scan, setScan] = useState<ScanState>({ status: "idle" });
  const [modelId, setModelId] = useState("");
  const [level, setLevel] = useState<BenchmarkLevel>("quick");
  const [run, setRun] = useState<RunState>({ status: "idle" });
  const [decisions, setDecisions] = useState<Array<LocalBenchDecisionRecord>>(
    [],
  );
  const runAlive = useRef(true);
  useEffect(() => {
    runAlive.current = true;
    let cancelled = false;
    void (async () => {
      try {
        const ids = await listConnectedProviders();
        if (cancelled) {
          return;
        }
        const local = getProviderCatalog().filter(
          (preset) => preset.kind === "local" && ids.includes(preset.id),
        );
        setRuntimes(
          local.map((preset) => ({
            id: preset.id,
            label: preset.label,
            endpoint: preset.baseUrl,
          })),
        );
      } catch {
        if (!cancelled) {
          setRuntimes([]);
        }
      }
    })();
    return () => {
      cancelled = true;
      runAlive.current = false;
    };
  }, []);

  const scanned = scan.status === "ready" ? scan : null;
  const canRun =
    scanned !== null && modelId.length > 0 && run.status !== "running";
  // R5: the run button stays disabled until a scan, with the reason shown.
  const runDisabledReason =
    run.status === "running"
      ? null
      : scanned === null
        ? t("settings.localbench.runNeedsScan")
        : modelId.length === 0
          ? t("settings.localbench.modelsEmpty")
          : null;
  const finished = run.status === "ready" ? run : null;

  async function handleScan(): Promise<void> {
    if (source === "folder") {
      const target = path.trim();
      if (target.length === 0 || scan.status === "scanning") {
        return;
      }
      setScan({ status: "scanning" });
      try {
        const result = await client.scanModels(target);
        setScan({ status: "ready", path: result.path, models: result.models });
        const first = result.models[0];
        setModelId(first === undefined ? "" : first.model_id);
        setRun({ status: "idle" });
        storeScanState(result.path, result.models);
      } catch {
        setScan({ status: "error" });
      }
      return;
    }
    // Runtime source: the attached runtime's real models, no folder.
    if (scan.status === "scanning" || client.scanRuntimeModels === undefined) {
      if (client.scanRuntimeModels === undefined) {
        setScan({ status: "error" });
      }
      return;
    }
    setScan({ status: "scanning" });
    try {
      const result = await client.scanRuntimeModels(source);
      setScan({ status: "ready", path: result.path, models: result.models });
      const first = result.models[0];
      setModelId(first === undefined ? "" : first.model_id);
      setRun({ status: "idle" });
      storeScanState(result.path, result.models);
    } catch {
      setScan({ status: "error" });
    }
  }

  // R5: the run shows progress (the running state while polling for
  // result rows) and ends on its result rows or a plain failure.
  async function handleRun(): Promise<void> {
    if (scanned === null || modelId.length === 0) {
      return;
    }
    setRun({ status: "running" });
    try {
      const estimate = await client.readEstimate(modelId, level);
      const runId = await client.startRun({ model_id: modelId, level });
      let rows: Array<LocalBenchResultRow> = [];
      for (let attempt = 0; attempt < 60; attempt += 1) {
        if (!runAlive.current) {
          return;
        }
        rows = (await client.readResults(runId)).filter(
          (row) => row.model_id === modelId,
        );
        if (rows.length > 0) {
          break;
        }
        await new Promise((resolve) => {
          setTimeout(resolve, 1000);
        });
      }
      if (!runAlive.current) {
        return;
      }
      const accepted: LocalBenchRunAccepted = {
        run_id: runId,
        estimated_duration_s: estimateSeconds(estimate),
        pc_load: LEVEL_PC_LOAD[level],
      };
      setRun({ status: "ready", accepted, rows });
      const first = rows[0];
      const record: LocalBenchDecisionRecord = {
        decision_id: runId,
        change: "run",
        run_id: runId,
        model_id: modelId,
        level,
        evidence: first === undefined ? "UNKNOWN" : kindToTier(first.kind),
        duration_s: accepted.estimated_duration_s,
        recorded_at: new Date().toISOString(),
      };
      const next = [...decisions, record];
      setDecisions(next);
      storeDecisionRecords(next);
    } catch {
      setRun({ status: "error" });
    }
  }

  return (
    <div data-testid="localbench-tab">
      {/* R5: scan source — a folder path or a connected local runtime
          (no folder needed). */}
      <div>
        <h3>{t("settings.localbench.sourceLabel")}</h3>
        <ul>
          <li>
            <label className="fx-radio-row">
              <input
                type="radio"
                data-testid="localbench-source-folder"
                name="localbench-source"
                checked={source === "folder"}
                onChange={() => setSource("folder")}
              />
              {t("settings.localbench.sourceFolder")}
            </label>
          </li>
          {(runtimes ?? []).map((runtime) => (
            <li key={runtime.id}>
              <label className="fx-radio-row">
                <input
                  type="radio"
                  data-testid={`localbench-source-${runtime.id}`}
                  name="localbench-source"
                  checked={source === runtime.id}
                  onChange={() => setSource(runtime.id)}
                />
                {t("settings.localbench.sourceRuntime", {
                  label: runtime.label,
                })}{" "}
                <span className="fx-quiet-line">{runtime.endpoint}</span>
              </label>
            </li>
          ))}
        </ul>
        {(runtimes ?? []).length === 0 ? (
          <p data-testid="localbench-runtime-none" className="fx-quiet-line">
            {t("settings.localbench.runtimeNone")}
          </p>
        ) : null}
      </div>
      <div>
        <label htmlFor="localbench-path">{t("settings.localbench.pathLabel")}</label>
        <input
          id="localbench-path"
          data-testid="localbench-path"
          type="text"
          value={path}
          placeholder={t("settings.localbench.pathHint")}
          onChange={(event) => setPath(event.target.value)}
        />
        <button
          type="button"
          data-testid="localbench-scan"
          className="fx-btn-quiet"
          disabled={
            (source === "folder" && path.trim().length === 0) ||
            scan.status === "scanning"
          }
          onClick={() => {
            void handleScan();
          }}
        >
          {t(
            scan.status === "scanning"
              ? "settings.localbench.scanning"
              : "settings.localbench.scanButton",
          )}
        </button>
      </div>
      {scan.status === "error" ? <p>{t("errors.generic")}</p> : null}
      <div>
        <h3>{t("settings.localbench.modelsTitle")}</h3>
        {scanned === null || scanned.models.length === 0 ? (
          <p>{t("settings.localbench.modelsEmpty")}</p>
        ) : (
          <ul>
            {scanned.models.map((model) => (
              <li key={model.model_id}>
                <label className="fx-radio-row">
                  <input
                    type="radio"
                    data-testid={`localbench-model-${model.model_id}`}
                    name="localbench-model"
                    checked={modelId === model.model_id}
                    onChange={() => setModelId(model.model_id)}
                  />
                  {model.display_name}
                </label>
                <span>{t(EVIDENCE_LOCALE_KEYS[model.evidence])}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3>{t("settings.localbench.levelLabel")}</h3>
        <ul>
          {BENCHMARK_LEVELS.map((option) => (
            <li key={option}>
              <label className="fx-radio-row">
                <input
                  type="radio"
                  data-testid={`localbench-level-${option}`}
                  name="localbench-level"
                  checked={level === option}
                  onChange={() => setLevel(option)}
                />
                {t(LEVEL_LOCALE_KEYS[option])}
              </label>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <button
          type="button"
          data-testid="localbench-run"
          className="fx-btn-primary"
          disabled={!canRun}
          onClick={() => {
            void handleRun();
          }}
        >
          {t(
            run.status === "running"
              ? "settings.localbench.running"
              : "settings.localbench.runButton",
          )}
        </button>
        {runDisabledReason !== null ? (
          <p data-testid="localbench-run-reason" className="fx-quiet-line">
            {runDisabledReason}
          </p>
        ) : null}
        {run.status === "error" ? <p>{t("errors.generic")}</p> : null}
      </div>
      {finished === null ? null : (
        <div data-testid="localbench-outcome">
          <p>
            {t("settings.localbench.durationEstimate", {
              seconds: formatNumber(finished.accepted.estimated_duration_s),
            })}
          </p>
          {finished.accepted.estimated_duration_s >= DURATION_WARNING_S ? (
            <p>{t("settings.localbench.durationWarning")}</p>
          ) : null}
          {finished.accepted.pc_load === "high" ? (
            <p>{t("settings.localbench.loadWarning")}</p>
          ) : null}
          <h3>{t("settings.localbench.resultsTitle")}</h3>
          {finished.rows.length === 0 ? (
            <p>{t("settings.localbench.resultsEmpty")}</p>
          ) : (
            <ul>
              {finished.rows.map((row) => (
                <li
                  key={row.case_id}
                  data-testid={`localbench-result-${row.case_id}`}
                >
                  <span>{row.case_id}</span>
                  <span>
                    {t("settings.localbench.colModel")}: {row.model_id}
                  </span>
                  <span>
                    {t("settings.localbench.colEvidence")}:{" "}
                    {t(EVIDENCE_LOCALE_KEYS[kindToTier(row.kind)])}
                  </span>
                  <span>{hardwareSummary(row.hardware)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <LocalBenchDecisionList decisions={decisions} />
    </div>
  );
}
