// Lane A project list page: project list plus add, open, pause, resume and
// archive. Add and archive are record calls (createProject, deleteProject);
// open selects the current project; pause and resume are local-only UI state
// because the served ProjectRecord carries no pause field, so they mutate no
// record. Mounted by the App route /projects in wave 3.

import { useEffect, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import type { ProjectRecord } from "../api/iface";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useApiClient, useCurrentProject } from "../app/ApiClientProvider";
import { t } from "../locale/index";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";

function isPaused(paused: ReadonlySet<string>, id: string): boolean {
  return paused.has(id);
}

export function ProjectsPage(): ReactElement {
  const client = useApiClient();
  const current = useCurrentProject();
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
          <form
            data-testid="project-add-form"
            onSubmit={(event) => {
              void submitAdd(event);
            }}
          >
            <input
              data-testid="project-add-name"
              aria-label={t("shell.topbar.project")}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
            <input
              data-testid="project-add-folder"
              aria-label={t("firstrun.steps.projectFolder")}
              value={folder}
              onChange={(event) => {
                setFolder(event.target.value);
              }}
            />
            <button type="submit" data-testid="project-add-submit">
              {t("tasks.creator.create")}
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
                      current.select(row.project_id);
                    }}
                  >
                    {row.name}
                  </button>
                  <span>{row.project_id}</span>
                  <span>{row.created_at}</span>
                  {isPaused(paused, row.project_id) ? (
                    <button
                      type="button"
                      data-testid={`project-resume-${row.project_id}`}
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
