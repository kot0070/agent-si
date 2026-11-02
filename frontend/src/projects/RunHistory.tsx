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
import {
  placementKey,
  placementForRow,
  resolveStatusHuman,
} from "../agents/agentsApi";
import { humanRunRef, buildRunRecords } from "./viewsApi";
import {
  formatRunMoment,
  humanDuration,
  readRuns,
  runStatusText,
  runWallS,
} from "./viewsApi";
import type { DevrunRun } from "./viewsApi";
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
          stateKey="projects.list.empty"
          actionKey={null}
          onAction={null}
        />
      ) : (
        <div>
          {runs.map((run) => {
            const short = humanRunRef(run.run_id);
            const wall = runWallS(run);
            const duration = humanDuration(wall);
            return (
              <div
                key={run.run_id}
                data-testid={`devrun-card-${run.run_id}`}
                className="fxpv-run"
              >
                <div>
                  {runStatusText(run)} · {formatRunMoment(run.start, locale)} ·{" "}
                  {duration ?? "not known"}
                </div>
                <div>
                  {run.parts.length === 0
                    ? "not known"
                    : run.parts
                        .map(
                          (part) =>
                            `${part.part_id}: ${part.verdict ?? "not known"}`,
                        )
                        .join(", ")}
                </div>
                <div>
                  Tokens{" "}
                  {run.tokens === "UNKNOWN"
                    ? "not known"
                    : formatNumber(run.tokens, locale)}{" "}
                  · Cost {run.cost === "UNKNOWN" ? "not known" : run.cost}
                </div>
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
                <div className="fxpv-quiet" title={short.title}>
                  {short.text}
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
            {parts.map((part) => {
              const short = humanRunRef(part.agent);
              return (
                <div
                  key={part.agent}
                  data-testid={`runhistory-part-${part.agent}`}
                  className="fxpv-row"
                >
                  <span title={short.title}>{short.text}</span>
                  <span>
                    {resolveStatusHuman(
                      readStatusHuman(part),
                      part.status,
                      locale,
                    )}
                  </span>
                  <span>{t(placementKey(placementForRow(part)))}</span>
                </div>
              );
            })}
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
