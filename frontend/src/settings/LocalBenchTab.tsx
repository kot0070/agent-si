// K07C LocalBench settings sub-lane: benchmark tab with the
// path -> scan -> level -> run flow. Duration and PC-load warnings come
// from the M3 estimate accepted for the run; per-model results render from
// the M3 result rows; the per-change decision record logs each finished
// run. Every visible string resolves through the locale; record data
// arrives only through LocalBenchClient.

import { useState } from "react";
import type { ReactElement } from "react";
import { formatNumber, t } from "../locale/index";
import type { LocalBenchClient } from "./LocalBenchClient";
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
  LocalBenchDecisionRecord,
  LocalBenchHardwareProfile,
  LocalBenchModel,
  LocalBenchResultRow,
  LocalBenchRunAccepted,
} from "./LocalBenchTypes";

export interface LocalBenchTabProps {
  client: LocalBenchClient;
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
  const [scan, setScan] = useState<ScanState>({ status: "idle" });
  const [modelId, setModelId] = useState("");
  const [level, setLevel] = useState<BenchmarkLevel>("quick");
  const [run, setRun] = useState<RunState>({ status: "idle" });
  const [decisions, setDecisions] = useState<Array<LocalBenchDecisionRecord>>(
    [],
  );

  const scanned = scan.status === "ready" ? scan : null;
  const canRun =
    scanned !== null && modelId.length > 0 && run.status !== "running";
  const finished = run.status === "ready" ? run : null;

  async function handleScan(): Promise<void> {
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
    } catch {
      setScan({ status: "error" });
    }
  }

  async function handleRun(): Promise<void> {
    if (scanned === null || modelId.length === 0) {
      return;
    }
    setRun({ status: "running" });
    try {
      const estimate = await client.readEstimate(modelId, level);
      const runId = await client.startRun({ model_id: modelId, level });
      const rows = (await client.readResults(runId)).filter(
        (row) => row.model_id === modelId,
      );
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
      setDecisions((records) => [...records, record]);
    } catch {
      setRun({ status: "error" });
    }
  }

  return (
    <div data-testid="localbench-tab">
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
          disabled={path.trim().length === 0 || scan.status === "scanning"}
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
                <label>
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
              <label>
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
    </div>
  );
}
