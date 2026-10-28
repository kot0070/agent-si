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
import { t, useLocale } from "../locale/index";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import {
  placementKey,
  placementForRow,
  resolveStatusHuman,
} from "../agents/agentsApi";

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
  const [report, setReport] = useState<PackageReport | "missing" | null>(null);
  const [failure, setFailure] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [nonce, setNonce] = useState(0);
  const [collapsed, setCollapsed] = useState(false);

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

  return (
    <Card
      cardId="run-history"
      titleKey="projects.runs.title"
      collapsed={collapsed}
      onToggle={(expanded) => {
        setCollapsed(!expanded);
      }}
    >
      {failure !== null ? (
        <ErrorPanel
          errorKey={failure.errorKey}
          code={failure.code}
          onRetry={() => {
            setNonce((value) => value + 1);
          }}
        />
      ) : ledger === null || parts === null ? (
        <LoadingState loadingKey="ui.loading.more" />
      ) : ledger.length === 0 ? (
        <EmptyState
          stateKey="projects.list.empty"
          actionKey={null}
          onAction={null}
        />
      ) : (
        <div>
          {ledger.map((row) => (
            <div
              key={row.package_id}
              data-testid={`runhistory-ledger-${row.package_id}`}
            >
              <span>{row.package_id}</span>
              <span>{t("agents.live.title")}</span>
              <span>{row.agents}</span>
              <span>{t("ui.card.total")}</span>
              <span>{row.peak_concurrency}</span>
              <span>{t("projects.time.title")}</span>
              <span>{row.wall_time_s}</span>
            </div>
          ))}
          <div>
            <span>{t("agents.live.title")}</span>
            {parts.map((part) => (
              <div key={part.agent} data-testid={`runhistory-part-${part.agent}`}>
                <span>{part.agent}</span>
                <span>
                  {resolveStatusHuman(
                    readStatusHuman(part),
                    part.status,
                    locale,
                  )}
                </span>
                <span>{t(placementKey(placementForRow(part)))}</span>
              </div>
            ))}
          </div>
          <div>
            <span>{t("projects.reports.title")}</span>
            {report === null || report === "missing" ? (
              <EmptyState
                stateKey="ui.table.empty"
                actionKey={null}
                onAction={null}
              />
            ) : (
              <div data-testid="runhistory-install">
                <span>{report.nudge}</span>
                <span>{String(report.auto_push)}</span>
                <span>{report.row.package_id}</span>
                <span>{report.row.agents}</span>
                <span>{report.row.peak_concurrency}</span>
                <span>{report.row.wall_time_s}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
