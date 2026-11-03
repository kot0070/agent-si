// Lane A TaskComposer: the guided composer posting to the projects tasks
// route (POST /api/v1/tasks through the shared ApiClient entry). Prefills
// the title from a stored task when initialTaskId names one; per A10 a late
// status load never overwrites a user-edited value (dirty-tracked fields).
// Numbers shown come from records only. The result line shows the typed
// title with a localized status (the id stays only as row key and testid);
// a successful create dispatches a tasks-changed window event so the tasks
// list refetches without a reload. Production caller: wave-3 App
// project-tasks route (CODER-5-Vale frontend/src/app/App.tsx); owned test
// mounts this component.

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import type { ApiClient } from "../api/iface";
import type { TaskRecord } from "../api/iface";
import { useApiClient } from "../app/ApiClientProvider";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";

export const TASK_SUBMIT_TIMEOUT_MS = 30000;

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
  CREATED: "tasks.status.queued",
};

export const TASKS_CHANGED_EVENT = "tasks-changed";

// FXUIB-B4: composer drafts live in sessionStorage per project (page
// change revives them; a restart starts clean).
function composerDraftKey(projectId: string, field: "title" | "scope"): string {
  return `fxcomposer.${field}.${projectId}`;
}

function readComposerDraft(projectId: string, field: "title" | "scope"): string {
  try {
    return window.sessionStorage.getItem(composerDraftKey(projectId, field)) ?? "";
  } catch {
    return "";
  }
}

function writeComposerDraft(projectId: string, field: "title" | "scope", value: string): void {
  try {
    if (value === "") {
      window.sessionStorage.removeItem(composerDraftKey(projectId, field));
    } else {
      window.sessionStorage.setItem(composerDraftKey(projectId, field), value);
    }
  } catch {
    return;
  }
}

export function taskStatusLabel(status: string): string {
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
  const [title, setTitle] = useState(() => readComposerDraft(props.projectId, "title"));
  const [scopeText, setScopeText] = useState(() => readComposerDraft(props.projectId, "scope"));
  const [loading, setLoading] = useState(props.initialTaskId != null);
  const [posting, setPosting] = useState(false);
  const [created, setCreated] = useState<TaskRecord | null>(null);
  const [blocking, setBlocking] = useState<BlockingError | null>(null);
  const [titleError, setTitleError] = useState(false);
  const dirtyTitleRef = useRef(false);
  const submitSeqRef = useRef(0);

  useEffect(() => {
    return () => {
      submitSeqRef.current += 1;
    };
  }, []);

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

  const handleCancel = (): void => {
    if (!posting) {
      return;
    }
    submitSeqRef.current += 1;
    setPosting(false);
  };

  const handleCreate = (): void => {
    if (posting) {
      return;
    }
    const nextTitle = title.trim();
    if (nextTitle === "") {
      // W4: empty submit never sends; the inline field error names the
      // missing title through the locale (no request, no raw codes).
      setTitleError(true);
      setBlocking(null);
      return;
    }
    setTitleError(false);
    const seq = submitSeqRef.current + 1;
    submitSeqRef.current = seq;
    setPosting(true);
    setBlocking(null);
    let finished = false;
    const timer = window.setTimeout(() => {
      if (finished || submitSeqRef.current !== seq) {
        return;
      }
      finished = true;
      submitSeqRef.current += 1;
      setPosting(false);
      setBlocking({ errorKey: "errors.generic", code: "UNKNOWN" });
    }, TASK_SUBMIT_TIMEOUT_MS);
    client
      .createTask(props.projectId, { title: nextTitle, scope: parseScope(scopeText) })
      .then(
        (task) => {
          if (finished || submitSeqRef.current !== seq) {
            return;
          }
          finished = true;
          window.clearTimeout(timer);
          setCreated(task);
          setPosting(false);
          window.dispatchEvent(
            new CustomEvent<{ projectId: string }>(TASKS_CHANGED_EVENT, {
              detail: { projectId: props.projectId },
            }),
          );
        },
        (error: unknown) => {
          if (finished || submitSeqRef.current !== seq) {
            return;
          }
          finished = true;
          window.clearTimeout(timer);
          if (error instanceof ApiError) {
            setBlocking({
              errorKey: apiErrorLocaleKey(error.code),
              code: error.code,
            });
          } else {
            setBlocking({ errorKey: "errors.generic", code: "UNKNOWN" });
          }
          setPosting(false);
        },
      );
  };

  return (
    <section data-testid="task-composer" aria-label={t("tasks.creator.title")}>
      <h2>{t("tasks.creator.title")}</h2>
      <p data-testid="task-composer-subtitle">{t("tasks.creator.subtitle")}</p>
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
            writeComposerDraft(props.projectId, "title", event.target.value);
            setTitleError(false);
          }}
        />
        {titleError ? (
          <span data-testid="composer-title-error" role="alert">
            {t("tasks.creator.titleRequired")}
          </span>
        ) : null}
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
            writeComposerDraft(props.projectId, "scope", event.target.value);
          }}
        />
      </label>
      {/* FXBTN: one spaced action row: create is the single primary,
          cancel reads quiet. */}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <button
        type="button"
        data-testid="composer-create"
        disabled={posting}
        onClick={handleCreate}
      >
        {t("tasks.creator.create")}
      </button>
      <button
        type="button"
        data-testid="composer-cancel"
        data-variant="quiet"
        disabled={!posting}
        onClick={handleCancel}
      >
        {t("tasks.creator.cancel")}
      </button>
      </div>
      {created !== null ? (
        <div data-testid="composer-result" key={created.task_id}>
          <span data-testid="composer-title-result">{created.title}</span>
          <span data-testid="composer-task-id" hidden>
            {created.task_id}
          </span>
          <span data-testid="composer-status">
            {taskStatusLabel(created.status)}
          </span>
        </div>
      ) : null}
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
