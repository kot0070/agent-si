// Lane A TaskComposer: the guided composer posting to the projects tasks
// route (POST /api/v1/tasks through the shared ApiClient entry). Prefills
// the title from a stored task when initialTaskId names one; per A10 a late
// status load never overwrites a user-edited value (dirty-tracked fields).
// Numbers shown come from records only. Production caller: wave-3 App
// project-tasks route (CODER-5-Vale frontend/src/app/App.tsx); owned test
// mounts this component.

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import type { ApiClient } from "../api/iface";
import type { TaskRecord } from "../api/iface";
import { useApiClient } from "../app/ApiClientProvider";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { t } from "../locale/index";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";

export interface TaskComposerProps {
  projectId: string;
  initialTaskId?: string | null;
}

interface BlockingError {
  errorKey: string;
  code: string;
}

const TASK_STATUS_KEYS: Record<string, string> = {
  QUEUED: "tasks.status.queued",
  RUNNING: "tasks.status.running",
  RETURNED: "tasks.status.returned",
  ACCEPTED: "tasks.status.accepted",
  REJECTED: "tasks.status.rejected",
  BLOCKED: "tasks.status.blocked",
  HANDOFF: "tasks.status.handoff",
};

function statusLabel(status: string): string {
  const key = TASK_STATUS_KEYS[status];
  return key === undefined ? status : t(key);
}

function parseScope(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

async function loadInitialTitle(
  client: ApiClient,
  taskId: string,
): Promise<string> {
  const task = await client.readTask(taskId);
  return task.title;
}

export function TaskComposer(props: TaskComposerProps): ReactElement {
  const client = useApiClient();
  const [title, setTitle] = useState("");
  const [scopeText, setScopeText] = useState("");
  const [loading, setLoading] = useState(props.initialTaskId != null);
  const [posting, setPosting] = useState(false);
  const [created, setCreated] = useState<TaskRecord | null>(null);
  const [blocking, setBlocking] = useState<BlockingError | null>(null);
  const dirtyTitleRef = useRef(false);

  useEffect(() => {
    let live = true;
    const initialTaskId = props.initialTaskId;
    if (initialTaskId == null) {
      setLoading(false);
      return () => {
        live = false;
      };
    }
    setLoading(true);
    loadInitialTitle(client, initialTaskId).then(
      (loadedTitle) => {
        if (!live) {
          return;
        }
        // A10: a late load applies only to fields the user never touched.
        if (!dirtyTitleRef.current) {
          setTitle(loadedTitle);
        }
        setLoading(false);
      },
      () => {
        if (!live) {
          return;
        }
        setLoading(false);
        setBlocking({ errorKey: "errors.generic", code: "CONTEXT_MISSING" });
      },
    );
    return () => {
      live = false;
    };
  }, [client, props.initialTaskId]);

  const handleCreate = (): void => {
    if (posting) {
      return;
    }
    const nextTitle = title.trim();
    if (nextTitle === "") {
      setBlocking({
        errorKey: "errors.generic",
        code: "CONTEXT_WRONG_CONTRACT_VERSION",
      });
      return;
    }
    setPosting(true);
    setBlocking(null);
    client
      .createTask(props.projectId, { title: nextTitle, scope: parseScope(scopeText) })
      .then(
        (task) => {
          setCreated(task);
        },
        (error: unknown) => {
          if (error instanceof ApiError) {
            setBlocking({
              errorKey: apiErrorLocaleKey(error.code),
              code: error.code,
            });
          } else {
            setBlocking({ errorKey: "errors.generic", code: "UNKNOWN" });
          }
        },
      )
      .finally(() => {
        setPosting(false);
      });
  };

  return (
    <section data-testid="task-composer" aria-label={t("tasks.creator.title")}>
      <h2>{t("tasks.creator.title")}</h2>
      {loading ? <LoadingState loadingKey="tasks.list.title" /> : null}
      <label>
        {t("tasks.creator.title")}
        <input
          data-testid="composer-title"
          type="text"
          placeholder={t("tasks.creator.title")}
          aria-label={t("tasks.creator.title")}
          value={title}
          onChange={(event) => {
            dirtyTitleRef.current = true;
            setTitle(event.target.value);
          }}
        />
      </label>
      <label>
        {t("agents.row.scope")}
        <input
          data-testid="composer-scope"
          type="text"
          placeholder={t("agents.row.scope")}
          aria-label={t("agents.row.scope")}
          value={scopeText}
          onChange={(event) => {
            setScopeText(event.target.value);
          }}
        />
      </label>
      <button
        type="button"
        data-testid="composer-create"
        disabled={posting}
        onClick={handleCreate}
      >
        {t("tasks.creator.create")}
      </button>
      {created !== null ? (
        <div data-testid="composer-result">
          <span data-testid="composer-task-id">{created.task_id}</span>
          <span data-testid="composer-status">
            {statusLabel(created.status)}
          </span>
        </div>
      ) : (
        <EmptyState
          stateKey="tasks.list.empty"
          actionKey={null}
          onAction={null}
        />
      )}
      {blocking !== null ? (
        <ErrorPanel
          errorKey={blocking.errorKey}
          code={blocking.code}
          onRetry={null}
        />
      ) : null}
    </section>
  );
}
