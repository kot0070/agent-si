// MH6A task view: the stored plan/action/observation triples of one task
// plus the used/limit turn-budget counter, all read from the turns route.
// Numbers and triple text come from route records only, never composed
// in the browser. Labels reuse existing locale keys only.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import type { TaskTurns } from "../api/projectsApi";
import { readTaskTurns } from "../api/projectsApi";
import { t } from "../locale/index";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";

export interface TaskViewProps {
  taskId: string;
}

export function TaskView(props: TaskViewProps): ReactElement {
  const [turns, setTurns] = useState<TaskTurns | null>(null);
  const [blocking, setBlocking] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setTurns(null);
    setBlocking(null);
    readTaskTurns(props.taskId).then(
      (loaded) => {
        if (live) {
          setTurns(loaded);
        }
      },
      (error: unknown) => {
        if (!live) {
          return;
        }
        if (error instanceof ApiError) {
          setBlocking(apiErrorLocaleKey(error.code));
        } else {
          setBlocking("errors.generic");
        }
      },
    );
    return () => {
      live = false;
    };
  }, [props.taskId]);

  return (
    <section data-testid="task-view" aria-label={t("tasks.list.title")}>
      <h2>{t("tasks.list.title")}</h2>
      {turns === null && blocking === null ? (
        <LoadingState loadingKey="tasks.list.title" />
      ) : null}
      {blocking !== null ? (
        <ErrorPanel errorKey={blocking} code="TURNS_READ" onRetry={null} />
      ) : null}
      {turns !== null ? (
        <p data-testid="task-turns-counter">
          {t("projects.runs.title")}: {turns.used} / {turns.limit}
        </p>
      ) : null}
      {turns !== null && turns.turns.length > 0 ? (
        <ol>
          {turns.turns.map((triple, index) => (
            <li key={index} data-testid={`task-turn-${index}`}>
              <div>
                <span>{t("agents.row.scope")}: </span>
                <span data-testid="task-turn-plan">{triple.plan}</span>
              </div>
              <div>
                <span>{t("projects.runs.title")}: </span>
                <span data-testid="task-turn-action">{triple.action}</span>
              </div>
              <div>
                <span>{t("agents.row.deliverable")}: </span>
                <span data-testid="task-turn-observation">
                  {triple.observation}
                </span>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      {turns !== null && turns.turns.length === 0 ? (
        <EmptyState stateKey="tasks.list.empty" actionKey={null} onAction={null} />
      ) : null}
    </section>
  );
}
