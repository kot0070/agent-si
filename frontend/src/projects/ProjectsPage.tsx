// Lane A project list page: project list plus add, open, pause, resume and
// archive. Add and archive are record calls (createProject, deleteProject);
// open selects the current project; pause and resume are local-only UI state
// because the served ProjectRecord carries no pause field, so they mutate no
// record. Mounted by the App route /projects in wave 3.
// The folder input gains a Choose control that fills the path from the
// sidecar native folder dialog (POST /api/v1/sidecar/pick-folder); the
// input stays editable and submits the typed path exactly as before, and
// the control hides itself when no native dialog exists (409).

import { useEffect, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { useNavigate } from "react-router-dom";
import type { ProjectRecord } from "../api/iface";
import { ApiError, apiErrorLocaleKey, requestResponse } from "../api/errors";
import { useApiClient, useCurrentProject } from "../app/ApiClientProvider";
import { hasChatUnseen, useUnseenVersion } from "../chat/index";
import { formatDate, t } from "../locale/index";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";

const FOLDER_PICK_URL = "/api/v1/sidecar/pick-folder";
const FOLDER_PICK_UNAVAILABLE = 409;

// FXKITUI labelled project form: every input carries a visible label plus
// a placeholder example. Keys are projectForm.<field>.label/.placeholder;
// EN defaults live in code as the fallback and the locale lane ships the
// uk lines from _task/FXKITUI/HITS.md. Locale files stay untouched.
export const PROJECT_FORM_KEYS = {
  nameLabel: "projectForm.name.label",
  namePlaceholder: "projectForm.name.placeholder",
  folderLabel: "projectForm.folder.label",
  folderPlaceholder: "projectForm.folder.placeholder",
} as const;

const PROJECT_FORM_EN: Record<string, string> = {
  [PROJECT_FORM_KEYS.nameLabel]: "Project name",
  [PROJECT_FORM_KEYS.namePlaceholder]: "My project",
  [PROJECT_FORM_KEYS.folderLabel]: "Project folder",
  [PROJECT_FORM_KEYS.folderPlaceholder]: "my-app-folder",
};

function projectFormText(key: string): string {
  try {
    return t(key);
  } catch {
    return PROJECT_FORM_EN[key] ?? key;
  }
}

function folderLabel(key: string, fallback: string): string {
  try {
    return t(key);
  } catch {
    return fallback;
  }
}

async function requestFolderPick(): Promise<string | null> {
  const response = await requestResponse(FOLDER_PICK_URL, {
    method: "POST",
    kind: "write",
    body: {},
  });
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (typeof data === "object" && data !== null) {
    const path = (data as { path?: unknown }).path;
    if (typeof path === "string" && path.length > 0) {
      return path;
    }
  }
  return null;
}

function isPaused(paused: ReadonlySet<string>, id: string): boolean {
  return paused.has(id);
}

// FXCHATHIST Part 2 (H3): isolated tests mount this page without a
// Router; open still selects there, navigation applies only with one.
function useOptionalNavigate(): ((to: string) => void) | null {
  try {
    return useNavigate();
  } catch {
    return null;
  }
}

function formatProjectDate(value: string): string {
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) {
    return value;
  }
  return formatDate(stamp);
}

export function ProjectsPage(): ReactElement {
  const client = useApiClient();
  const current = useCurrentProject();
  const navigate = useOptionalNavigate();
  // H4 quiet dot: re-renders rows when any slice flags unseen activity.
  const unseenTick = useUnseenVersion();
  void unseenTick;
  const [projects, setProjects] = useState<ProjectRecord[] | null>(null);
  const [failure, setFailure] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [nonce, setNonce] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const [paused, setPaused] = useState<ReadonlySet<string>>(new Set());
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [pickOpen, setPickOpen] = useState(true);

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const next = await client.listProjects();
        if (alive) {
          setProjects(next);
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
  }, [client, nonce]);

  async function submitAdd(event: FormEvent): Promise<void> {
    event.preventDefault();
    try {
      await client.createProject({ name, folder_ref: folder });
      if (name.length > 0 && folder.length > 0) {
        setName("");
        setFolder("");
      }
      setNonce((value) => value + 1);
    } catch (error) {
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

  async function chooseFolder(): Promise<void> {
    try {
      const picked = await requestFolderPick();
      if (picked !== null) {
        setFolder(picked);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === FOLDER_PICK_UNAVAILABLE) {
          setPickOpen(false);
          return;
        }
        setFailure({
          errorKey: apiErrorLocaleKey(error.code),
          code: error.code,
        });
      } else {
        setFailure({ errorKey: "errors.generic", code: "CONTEXT_MISSING" });
      }
    }
  }

  async function archive(id: string): Promise<void> {
    try {
      await client.deleteProject(id);
      setNonce((value) => value + 1);
    } catch (error) {
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

  function pause(id: string): void {
    setPaused((prev) => new Set(prev).add(id));
  }

  function resume(id: string): void {
    setPaused((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  return (
    <Card
      cardId="projects-list"
      titleKey="projects.list.title"
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
      ) : projects === null ? (
        <LoadingState loadingKey="ui.loading.more" />
      ) : (
        <div>
          <p data-testid="projects-list-subtitle">{t("projects.list.subtitle")}</p>
          <form
            data-testid="project-add-form"
            onSubmit={(event) => {
              void submitAdd(event);
            }}
          >
            <label htmlFor="project-add-name-input">
              {projectFormText(PROJECT_FORM_KEYS.nameLabel)}
              <input
                id="project-add-name-input"
                data-testid="project-add-name"
                aria-label={t("shell.topbar.project")}
                placeholder={projectFormText(PROJECT_FORM_KEYS.namePlaceholder)}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
            </label>
            <label htmlFor="project-add-folder-input">
              {projectFormText(PROJECT_FORM_KEYS.folderLabel)}
              <input
                id="project-add-folder-input"
                data-testid="project-add-folder"
                aria-label={t("firstrun.steps.projectFolder")}
                placeholder={projectFormText(PROJECT_FORM_KEYS.folderPlaceholder)}
                value={folder}
                onChange={(event) => {
                  setFolder(event.target.value);
                }}
              />
            </label>
            {pickOpen ? (
              <button
                type="button"
                data-testid="project-folder-choose"
                className="fx-btn-quiet"
                onClick={() => {
                  void chooseFolder();
                }}
              >
                {folderLabel("projects.folder.choose", "Choose folder")}
              </button>
            ) : null}
            <button type="submit" data-testid="project-add-submit">
              {t("projects.list.create")}
            </button>
          </form>
          {projects.length === 0 ? (
            <EmptyState
              stateKey="projects.list.empty"
              actionKey={null}
              onAction={null}
            />
          ) : (
            <ul>
              {projects.map((row) => (
                <li key={row.project_id} data-testid={`project-row-${row.project_id}`}>
                  <button
                    type="button"
                    data-testid={`project-open-${row.project_id}`}
                    onClick={() => {
                      // FXCHATHIST Part 2 (H3): opening a project
                      // selects it and lands on its chat history.
                      current.select(row.project_id);
                      navigate?.(`/projects/${row.project_id}/chat`);
                    }}
                  >
                    {row.name}
                  </button>
                  {/* FXCHATHIST Part 2 (H4): quiet dot while this
                      project's chat holds unseen activity. */}
                  {hasChatUnseen(client, row.project_id) ? (
                    <span
                      data-testid={`project-chat-dot-${row.project_id}`}
                      className="fx-quiet"
                      aria-hidden="true"
                    >
                      {"\u2022"}
                    </span>
                  ) : null}
                  <span data-testid={`project-created-${row.project_id}`}>
                    {formatProjectDate(row.created_at)}
                  </span>
                  {isPaused(paused, row.project_id) ? (
                    <button
                      type="button"
                      data-testid={`project-resume-${row.project_id}`}
                      className="fx-btn-quiet"
                      onClick={() => {
                        resume(row.project_id);
                      }}
                    >
                      {t("ui.error.retry")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      data-testid={`project-pause-${row.project_id}`}
                      className="fx-btn-quiet"
                      onClick={() => {
                        pause(row.project_id);
                      }}
                    >
                      {t("chat.abort.cancel")}
                    </button>
                  )}
                  <button
                    type="button"
                    data-testid={`project-archive-${row.project_id}`}
                    className="fx-btn-quiet"
                    onClick={() => {
                      void archive(row.project_id);
                    }}
                  >
                    {t("shell.closing.leave")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
