// Lane A live agents panel: who, where, deliverable and human status per
// agent with LOCAL/SPLIT/CLOUD badges, updating without reload. Mounted by
// the App route /agents/live in wave 3; the Inspector embeds it as compact
// self-scrolling content. Every number shown is an exact row count; every
// string is a locale lookup or served record data.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import type { PartRow } from "../api/iface";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useApiClient } from "../app/ApiClientProvider";
import { t, useLocale } from "../locale/index";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import {
  PLACEMENTS,
  countPlacements,
  placementForRow,
  placementKey,
  resolveStatusHuman,
  shortenLiveRef,
} from "./agentsApi";

export interface AgentsLiveProps {
  projectId: string;
}

interface LiveSubscriber {
  subscribe?: (listener: (rows: PartRow[]) => void) => () => void;
}

const POLL_MS = 2000;

function readStatusHuman(row: PartRow): unknown {
  return (row as unknown as Record<string, unknown>).status_human;
}

function readLiveExtra(row: PartRow, name: string): unknown {
  return (row as unknown as Record<string, unknown>)[name];
}

function formatLiveText(value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "–";
  }
  return String(value);
}

function formatLiveTokens(value: unknown): string {
  if (typeof value !== "object" || value === null) {
    return "–";
  }
  const record = value as Record<string, unknown>;
  const input = record.input;
  const output = record.output;
  if (typeof input !== "number" && typeof output !== "number") {
    return "–";
  }
  const left = typeof input === "number" ? String(input) : "–";
  const right = typeof output === "number" ? String(output) : "–";
  return `${left}/${right}`;
}

function formatLiveList(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) {
    return "–";
  }
  return value.map((item) => String(item)).join(", ");
}

export function AgentsLive(props: AgentsLiveProps): ReactElement {
  const client = useApiClient();
  const { locale } = useLocale();
  const [rows, setRows] = useState<PartRow[] | null>(null);
  const [projectName, setProjectName] = useState<string | null>(null);
  const [failure, setFailure] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [nonce, setNonce] = useState(0);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let alive = true;
    let stop: (() => void) | undefined;
    let timer: ReturnType<typeof setInterval> | undefined;
    async function load(): Promise<void> {
      try {
        const next = await client.listAgentsLive();
        if (alive) {
          setRows(next);
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
    const source = client as unknown as LiveSubscriber;
    if (typeof source.subscribe === "function") {
      stop = source.subscribe((next) => {
        if (alive) {
          setRows([...next]);
        }
      });
    } else {
      timer = setInterval(() => {
        void load();
      }, POLL_MS);
    }
    return () => {
      alive = false;
      if (stop !== undefined) {
        stop();
      }
      if (timer !== undefined) {
        clearInterval(timer);
      }
    };
  }, [client, nonce]);

  useEffect(() => {
    let alive = true;
    client.readProject(props.projectId).then(
      (project) => {
        if (alive) {
          setProjectName(project.name);
        }
      },
      () => {
        if (alive) {
          setProjectName(null);
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [client, props.projectId]);

  const counts = countPlacements(rows ?? []);

  return (
    <Card
      cardId="agents-live"
      titleKey="agents.live.title"
      collapsed={collapsed}
      onToggle={(expanded) => {
        setCollapsed(!expanded);
      }}
    >
      <div>
        <span>{t("shell.topbar.project")}</span>
        <span data-testid="agents-live-project">{projectName ?? t("shell.topbar.project")}</span>
      </div>
      <div>
        {PLACEMENTS.map((placement) => (
          <span key={placement} data-testid={`agent-badge-${placement}`}>
            {t(placementKey(placement))} {counts[placement]}
          </span>
        ))}
      </div>
      {failure !== null ? (
        <ErrorPanel
          errorKey={failure.errorKey}
          code={failure.code}
          onRetry={() => {
            setNonce((value) => value + 1);
          }}
        />
      ) : rows === null ? (
        <LoadingState loadingKey="ui.loading.more" />
      ) : rows.length === 0 ? (
        <EmptyState
          stateKey="agents.live.empty"
          actionKey={null}
          onAction={null}
        />
      ) : (
        <div
          data-testid="agents-live-rows"
          style={{ maxHeight: "240px", overflowY: "auto", overflowX: "hidden" }}
        >
          {rows.map((row) => {
            const placement = placementForRow(row);
            const scopeRef = shortenLiveRef(row.scope);
            const deliverableRef = shortenLiveRef(row.deliverable);
            return (
              <div key={row.agent} data-testid={`agent-row-${row.agent}`}>
                <span data-testid={`agent-row-who-${row.agent}`}>
                  {row.agent}
                </span>
                <span className="fx-live-pair">
                  <span className="fx-live-label">
                    {t("agents.row.scope")}
                  </span>{" "}
                  <span title={scopeRef.title}>{scopeRef.text}</span>
                </span>
                <span className="fx-live-pair">
                  <span className="fx-live-label">
                    {t("agents.row.deliverable")}
                  </span>{" "}
                  <span title={deliverableRef.title}>
                    {deliverableRef.text}
                  </span>
                </span>
                <span className="fx-live-pair">
                  <span className="fx-live-label">
                    {t("settings.roleProfile.providerLabel")}
                  </span>{" "}
                  <span>
                    {formatLiveText(readLiveExtra(row, "provider"))}
                  </span>
                </span>
                <span>
                  {resolveStatusHuman(readStatusHuman(row), row.status, locale)}
                </span>
                <span data-testid={`agent-row-place-${row.agent}`}>
                  {t(placementKey(placement))}
                </span>
                <div
                  data-testid={`agent-row-detail-${row.agent}`}
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "4px 12px",
                    fontSize: "12px",
                    opacity: 0.85,
                  }}
                >
                  <span>
                    {t("settings.roleProfile.roleLabel")}{" "}
                    {formatLiveText(readLiveExtra(row, "role"))}
                  </span>
                  <span>
                    {t("settings.roleProfile.modelLabel")}{" "}
                    {formatLiveText(readLiveExtra(row, "model"))}
                  </span>
                  <span>step {formatLiveText(readLiveExtra(row, "step"))}</span>
                  <span>file {formatLiveText(readLiveExtra(row, "file"))}</span>
                  <span>
                    {t("telemetry.cost")}{" "}
                    {formatLiveText(readLiveExtra(row, "cost"))}
                  </span>
                  <span>
                    {t("agents.row.tokens")}{" "}
                    {formatLiveTokens(readLiveExtra(row, "tokens"))}
                  </span>
                  <span>
                    context {formatLiveText(readLiveExtra(row, "context"))}
                  </span>
                  <span>
                    {t("projects.errors.title")}{" "}
                    {formatLiveList(readLiveExtra(row, "errors"))}
                  </span>
                  <span>
                    waits {formatLiveList(readLiveExtra(row, "waits"))}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
