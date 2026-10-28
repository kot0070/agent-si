// Lane A project extended views: overview, tasks, runs, time, AI usage,
// tokens, cost, local AI, cloud AI, models, routing decisions (WHY_THIS_MODEL
// from the stored snapshot), audits, errors and reports. Numbers render only
// from served records; served token or audit telemetry has no route, so those
// views stay honestly empty until one lands. The reports export serializes
// stored telemetry; derived narrative lines carry the DERIVED label and never
// override measured rows. Mounted by the App routes
// /projects/:projectId/* in wave 3.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import type {
  BudgetState,
  LedgerRow,
  PartRow,
  ProjectRecord,
  RoutingWhy,
  TaskRecord,
} from "../api/iface";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useApiClient } from "../app/ApiClientProvider";
import { t, useLocale } from "../locale/index";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import {
  PartStatusSchema,
  placementKey,
  resolveStatusHuman,
  statusHumanKey,
} from "../agents/agentsApi";
import {
  PROJECT_VIEWS,
  buildReportNarrative,
  computeAgeDays,
  CONTEXT_SOURCE,
  contextUsage,
  exportProjectReport,
  projectMenuTestId,
  projectViewTitleKey,
  remainingBudget,
  splitRowsByPlacement,
  sumLedger,
} from "./projectsApi";
import type { ProjectViewName } from "./projectsApi";
import { RunHistory } from "./RunHistory";
import { HealthView } from "./observe/HealthView";
import { MatrixView } from "./observe/MatrixView";
import { VerifierView } from "./observe/VerifierView";
import { classifyScope } from "./scope";

export type { ProjectViewName };
export { PROJECT_VIEWS };

export interface ProjectViewProps {
  projectId: string;
  view: ProjectViewName;
  decisionId?: string;
  onSelect?: (view: ProjectViewName) => void;
}

interface ViewData {
  project: ProjectRecord;
  tasks: TaskRecord[];
  ledger: LedgerRow[];
  budget: BudgetState;
  live: PartRow[];
  why: RoutingWhy | null;
}

function readStatusHuman(row: PartRow): unknown {
  return (row as unknown as Record<string, unknown>).status_human;
}

function Fact(props: {
  testId: string;
  labelKey: string;
  value: string | number;
}): ReactElement {
  return (
    <div data-testid={props.testId}>
      <span>{t(props.labelKey)}</span>
      <span>{props.value}</span>
    </div>
  );
}

export function ProjectView(props: ProjectViewProps): ReactElement {
  const client = useApiClient();
  const { locale } = useLocale();
  const [data, setData] = useState<ViewData | null>(null);
  const [report, setReport] = useState<string | null>(null);
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
        const [project, tasks, ledger, budget, live] = await Promise.all([
          client.readProject(props.projectId),
          client.listTasks(props.projectId),
          client.readLedger(props.projectId),
          client.readBudget(props.projectId),
          client.listAgentsLive(),
        ]);
        let why: RoutingWhy | null = null;
        if (
          (props.view === "routing-decisions" || props.view === "models") &&
          props.decisionId !== undefined
        ) {
          why = await client.readRoutingWhy(props.decisionId);
        }
        let exported: string | null = null;
        if (props.view === "reports") {
          exported = await exportProjectReport(client, props.projectId);
        }
        if (alive) {
          setData({ project, tasks, ledger, budget, live, why });
          setReport(exported);
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
  }, [client, props.projectId, props.view, props.decisionId, nonce]);

  function renderContent(): ReactElement {
    if (data === null) {
      if (failure !== null) {
        return (
          <ErrorPanel
            errorKey={failure.errorKey}
            code={failure.code}
            onRetry={() => {
              setNonce((value) => value + 1);
            }}
          />
        );
      }
      return <LoadingState loadingKey="ui.loading.more" />;
    }
    const sums = sumLedger(data.ledger);
    switch (props.view) {
      case "overview": {
        const age = computeAgeDays(data.project.created_at, Date.now());
        return (
          <div>
            <Fact
              testId="overview-name"
              labelKey="shell.topbar.project"
              value={data.project.name}
            />
            <Fact
              testId="overview-created"
              labelKey="chat.stream.timestamp"
              value={data.project.created_at}
            />
            {age === null ? (
              <EmptyState
                stateKey="ui.table.empty"
                actionKey={null}
                onAction={null}
              />
            ) : (
              <Fact
                testId="overview-age-days"
                labelKey="projects.time.title"
                value={age}
              />
            )}
            <Fact
              testId="overview-task-count"
              labelKey="tasks.list.title"
              value={data.tasks.length}
            />
            <Fact
              testId="overview-package-count"
              labelKey="projects.runs.title"
              value={sums.packages}
            />
            <Fact
              testId="overview-agents-total"
              labelKey="agents.live.title"
              value={sums.agents}
            />
            <Fact
              testId="overview-peak-max"
              labelKey="ui.card.total"
              value={sums.peak}
            />
            <Fact
              testId="overview-wall-total"
              labelKey="projects.time.title"
              value={sums.wall}
            />
            <Fact
              testId="overview-budget-spent"
              labelKey="telemetry.cost"
              value={data.budget.spent}
            />
            <Fact
              testId="overview-budget-remaining"
              labelKey="projects.derived.label"
              value={remainingBudget(data.budget)}
            />
          </div>
        );
      }
      case "tasks": {
        if (data.tasks.length === 0) {
          return (
            <EmptyState
              stateKey="tasks.list.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {data.tasks.map((task) => (
              <div key={task.task_id} data-testid={`task-row-${task.task_id}`}>
                <span>{task.title}</span>
                <span>
                  {(() => {
                    const checked = PartStatusSchema.safeParse(task.status);
                    return checked.success
                      ? t(statusHumanKey(checked.data))
                      : task.status;
                  })()}
                </span>
                <span>{task.created_at}</span>
              </div>
            ))}
          </div>
        );
      }
      case "runs": {
        return (
          <RunHistory
            projectId={props.projectId}
            packageId={data.ledger[0]?.package_id}
          />
        );
      }
      case "time": {
        if (data.ledger.length === 0) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {data.ledger.map((row) => (
              <div key={row.package_id} data-testid={`time-row-${row.package_id}`}>
                <span>{row.package_id}</span>
                <span>{row.wall_time_s}</span>
              </div>
            ))}
            <Fact
              testId="time-wall-total"
              labelKey="projects.time.title"
              value={sums.wall}
            />
          </div>
        );
      }
      case "ai-usage": {
        return (
          <div>
            <Fact
              testId="usage-agents-total"
              labelKey="agents.live.title"
              value={sums.agents}
            />
            <Fact
              testId="usage-peak-max"
              labelKey="ui.card.total"
              value={sums.peak}
            />
            <Fact
              testId="usage-wall-total"
              labelKey="projects.time.title"
              value={sums.wall}
            />
            <MatrixView rows={data.live} />
          </div>
        );
      }
      case "tokens": {
        return (
          <EmptyState
            stateKey="ui.table.empty"
            actionKey={null}
            onAction={null}
          />
        );
      }
      case "cost": {
        const usage = contextUsage(data.budget);
        return (
          <div>
            <div data-testid="context-card">
              <span>{t("projects.tokens.title")}</span>
              <span data-testid="context-remaining">{usage.remaining}</span>
              <span data-testid="context-total">{usage.total}</span>
              <span data-testid="context-source">{CONTEXT_SOURCE}</span>
            </div>
            <Fact
              testId="cost-spent"
              labelKey="telemetry.cost"
              value={data.budget.spent}
            />
            <Fact
              testId="cost-reserved"
              labelKey="projects.cost.title"
              value={data.budget.reserved}
            />
            <Fact
              testId="cost-limit"
              labelKey="ui.card.total"
              value={data.budget.hard_limit}
            />
            <Fact
              testId="cost-remaining"
              labelKey="projects.derived.label"
              value={remainingBudget(data.budget)}
            />
            <HealthView ledger={data.ledger} budget={data.budget} />
          </div>
        );
      }
      case "local-ai":
      case "cloud-ai": {
        const wanted = props.view === "local-ai" ? "LOCAL" : "CLOUD";
        const rows = splitRowsByPlacement(data.live)[wanted];
        if (rows.length === 0) {
          return (
            <EmptyState
              stateKey="agents.live.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {rows.map((row) => (
              <div key={row.agent} data-testid={`place-row-${row.agent}`}>
                <span>{row.agent}</span>
                <span>{row.scope}</span>
                <span data-testid={`scope-kind-${row.agent}`}>
                  {classifyScope(row.scope)}
                </span>
                <span>
                  {resolveStatusHuman(
                    readStatusHuman(row),
                    row.status,
                    locale,
                  )}
                </span>
                <span>{t(placementKey(wanted))}</span>
              </div>
            ))}
          </div>
        );
      }
      case "models": {
        if (data.why === null) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {data.why.assignments.map((assignment, index) => (
              <div key={index} data-testid={`model-row-${index}`}>
                <span>
                  {assignment.provider_id}/{assignment.model} {assignment.role}
                </span>
              </div>
            ))}
          </div>
        );
      }
      case "routing-decisions": {
        if (data.why === null) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            <div data-testid="why-this-model">
              <span>{t("projects.why_this_model.title")}</span>
              <span data-testid="why-this-model-reason">
                {data.why.reason.fit_basis}
              </span>
              <span>{data.why.reason.task_class}</span>
              <span>{data.why.reason.price_basis}</span>
              <span>{data.why.reason.quality_basis}</span>
              {data.why.reason.rejected.map((name) => (
                <span key={name}>{name}</span>
              ))}
            </div>
            <div data-testid="why-version">
              <span>{t("projects.routing.title")}</span>
              <span>{data.why.decision.policy_ref}</span>
            </div>
            <div data-testid="why-candidates">
              <span>{t("projects.models.title")}</span>
              {data.why.assignments.length === 0 ? (
                <EmptyState
                  stateKey="ui.table.empty"
                  actionKey={null}
                  onAction={null}
                />
              ) : (
                data.why.assignments.map((assignment, index) => (
                  <div key={index} data-testid={`why-candidate-${index}`}>
                    <span>
                      {assignment.provider_id}/{assignment.model}{" "}
                      {assignment.role}
                    </span>
                  </div>
                ))
              )}
            </div>
            <div data-testid="why-provenance">
              <span>{data.why.snapshot.snapshot_ref}</span>
              <span>{data.why.snapshot.captured_at}</span>
            </div>
            <div data-testid="why-this-model-decision">
              <span>{data.why.decision.decision_id}</span>
              <span>{data.why.decision.policy_ref}</span>
              <span>{data.why.snapshot.snapshot_ref}</span>
            </div>
            <VerifierView why={data.why} />
          </div>
        );
      }
      case "audits": {
        return (
          <EmptyState
            stateKey="ui.table.empty"
            actionKey={null}
            onAction={null}
          />
        );
      }
      case "errors": {
        return (
          <EmptyState
            stateKey="ui.table.empty"
            actionKey={null}
            onAction={null}
          />
        );
      }
      case "reports": {
        return (
          <div>
            <pre data-testid="project-report-export">{report ?? ""}</pre>
            <div data-testid="project-report-derived">
              <span>{t("projects.derived.label")}</span>
              {buildReportNarrative({
                tasks: data.tasks,
                ledger: data.ledger,
                budget: data.budget,
              }).map((line) => (
                <span key={line}>{line}</span>
              ))}
            </div>
          </div>
        );
      }
    }
  }

  return (
    <div>
      <nav>
        {PROJECT_VIEWS.map((name) => (
          <button
            key={name}
            type="button"
            data-testid={projectMenuTestId(name)}
            onClick={() => {
              props.onSelect?.(name);
            }}
          >
            {t(projectViewTitleKey(name))}
          </button>
        ))}
      </nav>
      <Card
        cardId={`project-${props.view}`}
        titleKey={projectViewTitleKey(props.view)}
        collapsed={collapsed}
        onToggle={(expanded) => {
          setCollapsed(!expanded);
        }}
      >
        {failure !== null && props.view !== "errors" ? (
          <ErrorPanel
            errorKey={failure.errorKey}
            code={failure.code}
            onRetry={() => {
              setNonce((value) => value + 1);
            }}
          />
        ) : (
          renderContent()
        )}
      </Card>
    </div>
  );
}
