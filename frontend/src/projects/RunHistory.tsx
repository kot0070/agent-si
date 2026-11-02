// Lane A runs ledger view: stored ledger rows, a parts card with human end
// reasons, and an install card with the next-package nudge report. Every
// number shown is a served record cell; human reasons map served statuses
// through tasks.status.*. Mounted by ProjectView (runs view) and by the App
// route /projects/:projectId/runs in wave 3.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import type {
  LedgerRow,
  PackageReport,
  PartRow,
} from "../api/iface";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useApiClient } from "../app/ApiClientProvider";
import { formatNumber, t, useLocale } from "../locale/index";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import { placementKey, resolveStatusHuman } from "../agents/agentsApi";
import { humanRunRef, buildRunRecords, dedupeLiveRows } from "./viewsApi";
import {
  formatRunMoment,
  humanDuration,
  readRuns,
  runStatusText,
  runWallS,
} from "./viewsApi";
import type { DevrunRun } from "./viewsApi";
import { RunId } from "./RunId";
import "./projectview.css";

export interface RunHistoryProps {
  projectId: string;
  packageId?: string;
}

function readStatusHuman(row: PartRow): unknown {
  return (row as unknown as Record<string, unknown>).status_human;
}

export function RunHistory(props: RunHistoryProps): ReactElement {
  const client = useApiClient();
  const { locale } = useLocale();
  const [ledger, setLedger] = useState<LedgerRow[] | null>(null);
  const [parts, setParts] = useState<PartRow[] | null>(null);
  const [runs, setRuns] = useState<DevrunRun[] | null>(null);
  const [report, setReport] = useState<PackageReport | "missing" | null>(null);
  const [failure, setFailure] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const [rows, live] = await Promise.all([
          client.readLedger(props.projectId),
          client.listAgentsLive(),
        ]);
        const target = props.packageId ?? rows[0]?.package_id ?? null;
        let nudge: PackageReport | "missing" = "missing";
        if (target !== null) {
          try {
            nudge = await client.readNextPackageNudge(target);
          } catch {
            nudge = "missing";
          }
        }
        if (alive) {
          setLedger(rows);
          setParts(live);
          setReport(nudge);
          setFailure(null);
        }
      } catch (error) {
        if (alive) {
          if (error instanceof ApiError) {
            setFailure({
              errorKey: apiErrorLocaleKey(error.code),
              code: error.code,
            });
          } else {
            setFailure({ errorKey: "errors.generic", code: "CONTEXT_MISSING" });
          }
        }
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [client, props.projectId, props.packageId, nonce]);

  // FXVIEWS3: the same route serves devrun run rows under the "runs" key
  // (FXVIEWS2); readRuns reads that key. A missing doc reads [] (honestly
  // empty) so a failing enrichment never hides the ledger rows.
  useEffect(() => {
    let alive = true;
    void readRuns(props.projectId).then((rows) => {
      if (alive) {
        setRuns(rows);
      }
    });
    return () => {
      alive = false;
    };
  }, [props.projectId, nonce]);

  return (
    <div>
      {failure !== null ? (
        <ErrorPanel
          errorKey={failure.errorKey}
          code={failure.code}
          onRetry={() => {
            setNonce((value) => value + 1);
          }}
        />
      ) : ledger === null || parts === null || runs === null ? (
        <LoadingState loadingKey="ui.loading.more" />
      ) : ledger.length === 0 && runs.length === 0 ? (
        <EmptyState
          stateKey="projects.runs.empty"
          actionKey={null}
          onAction={null}
        />
      ) : (
        <div>
          {runs.map((run) => {
            const wall = runWallS(run);
            const duration = humanDuration(wall);
            // FXTABS T6: the header names what failed: the served duration
            // when known, else the run summary or the first part reason,
            // never a bare "not known" next to "failed".
            const firstReason = run.parts
              .map((part) => part.reason)
              .find(
                (reason) => reason !== undefined && reason !== "",
              );
            const outcome =
              duration ??
              (run.summary !== "" ? run.summary : (firstReason ?? null));
            return (
              <div
                key={run.run_id}
                data-testid={`devrun-card-${run.run_id}`}
                className="fxpv-run"
              >
                <div>
                  {runStatusText(run)} · {formatRunMoment(run.start, locale)} ·{" "}
                  {outcome ?? t("shell.common.unknown")}
                </div>
                <div>
                  {run.parts.length === 0
                    ? t("shell.common.unknown")
                    : run.parts
                        .map((part) =>
                          part.verdict === undefined || part.verdict === null
                            ? (part.attempts ?? 0) > 0
                              ? `${part.part_id}: ${t("shell.common.unknown")}`
                              : `${part.part_id}: ${t("projectView.runs.notRun")}`
                            : `${part.part_id}: ${part.verdict}`,
                        )
                        .join(", ")}
                </div>
                <div>
                  Tokens{" "}
                  {run.tokens === "UNKNOWN"
                    ? "not known"
                    : formatNumber(run.tokens, locale)}{" "}
                  · Cost{" "}
                  {run.cost === "UNKNOWN"
                    ? t("projectView.cost.notKnown")
                    : run.cost}
                </div>
                {run.folder ? (
                  <div
                    data-testid={`devrun-folder-${run.run_id}`}
                    className="fx-quiet fx-truncate"
                    title={run.folder}
                  >
                    {run.folder}
                  </div>
                ) : null}
                {run.summary === "" ? null : <div>{run.summary}</div>}
                {run.files.length === 0 ? null : (
                  <ul>
                    {run.files.map((file) => (
                      <li key={file} title={file}>
                        {humanRunRef(file).text}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="fxpv-quiet">
                  <RunId id={run.run_id} />
                </div>
              </div>
            );
          })}
          {ledger.map((row) => {
            const short = humanRunRef(row.package_id);
            return (
              <div
                key={row.package_id}
                data-testid={`runhistory-ledger-${row.package_id}`}
                className="fxpv-row"
              >
                <span>{t("projectView.runs.package")}</span>
                <span title={short.title}>{short.text}</span>
                <span>{t("projectView.runs.agents")}</span>
                <span>{row.agents}</span>
                <span>{t("projectView.runs.peak")}</span>
                <span>{row.peak_concurrency}</span>
                <span>{t("projectView.runs.wall")}</span>
                <span>{row.wall_time_s}</span>
              </div>
            );
          })}
          <div>
            <p>Team</p>
            {(() => {
              // FXTABS T6: one row per agent with its last status (the fold
              // lives in dedupeLiveRows); when the latest run ended, a stale
              // served RUNNING reads as the run's end state, never Running.
              const latest =
                runs.length === 0 ? null : runs[runs.length - 1] ?? null;
              const latestEnded =
                latest !== null && runWallS(latest) !== null;
              return dedupeLiveRows(parts).map((row) => {
                const source =
                  parts.find(
                    (candidate) =>
                      candidate.agent === row.agent &&
                      candidate.status === row.status &&
                      readStatusHuman(candidate) !== undefined,
                  ) ??
                  parts.find(
                    (candidate) =>
                      candidate.agent === row.agent &&
                      candidate.status === row.status,
                  ) ??
                  parts.find((candidate) => candidate.agent === row.agent);
                const stale =
                  latestEnded && row.status === "RUNNING" && latest !== null;
                // FXTABS U5c: the team row names the served role (or the
                // role the agent id carries), never a bare agent id; the
                // agent id rides the title. Repeats are folded with a count.
                const roleMatch = /^([A-Za-z]+)-/.exec(row.agent);
                const roleKey =
                  row.role !== undefined
                    ? row.role.toLowerCase()
                    : (roleMatch?.[1]?.toLowerCase() ?? null);
                const roleName =
                  roleKey === "director" ||
                  roleKey === "manager" ||
                  roleKey === "worker" ||
                  roleKey === "auditor" ||
                  roleKey === "watcher"
                    ? t(`providers.role.${roleKey}`)
                    : null;
                return (
                  <div
                    key={row.agent}
                    data-testid={`runhistory-part-${row.agent}`}
                    className="fxpv-row"
                  >
                    <span title={roleName === null ? undefined : row.agent}>
                      {roleName ?? row.agent}
                    </span>
                    {row.attempts > 1 ? (
                      <span>
                        {t("projectView.attempts", { count: row.attempts })}
                      </span>
                    ) : null}
                    <span>
                      {stale
                        ? runStatusText(latest)
                        : resolveStatusHuman(
                            source === undefined
                              ? undefined
                              : readStatusHuman(source),
                            row.status,
                            locale,
                          )}
                    </span>
                    <span>{t(placementKey(row.placement))}</span>
                  </div>
                );
              });
            })()}
          </div>
          <div>
            {buildRunRecords({ ledger, live: parts }).map((record) => {
              const short = humanRunRef(record.packageId);
              return (
                <div
                  key={record.packageId}
                  data-testid={`runrecord-${record.packageId}`}
                  className="fxpv-row"
                >
                  <span>{t("projectView.runs.package")}:</span>
                  <span title={short.title}>{short.text}</span>
                  <span>{record.agents}</span>
                  <span>{record.peak}</span>
                  <span>{record.wallTimeS}</span>
                  <span>{t("shell.common.unknown")}</span>
                </div>
              );
            })}
          </div>
          <div>
            {report === null || report === "missing" ? null : (
              <div data-testid="runhistory-install" className="fxpv-row">
                <span>{t("projectView.runs.package")}</span>
                <span>{humanRunRef(report.row.package_id).text}</span>
                <span>{report.nudge}</span>
                <span>{report.row.agents}</span>
                <span>{report.row.peak_concurrency}</span>
                <span>{report.row.wall_time_s}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
