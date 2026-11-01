import { useState } from 'react';
import type { FormEvent, ReactElement } from 'react';
import { Link, useInRouterContext } from 'react-router-dom';
import { t } from '../../locale/index';
import { ApiError, apiErrorLocaleKey, requestResponse } from '../../api/errors';
import type { ApiClient, TaskRecord } from '../../api/iface';
import { useApiClient, useCurrentProject } from '../ApiClientProvider';
import type { CurrentProject } from '../ApiClientProvider';
import { saveRoleProfile } from '../../settings/index';
import { ROLE_PROFILE_ROLES } from '../../settings/roleProfilesApi';
import { ErrorPanel } from '../../ui/ErrorPanel';

export type FirstRunStep = 'connectProvider' | 'oneClickTeam' | 'projectFolder' | 'firstTask';

export type OptionalFirstRunStep = 'localAI' | 'watcherPreset' | 'automations' | 'kbs';

export interface FirstRunFlowProps {
  initialStep?: FirstRunStep;
  onComplete: () => void;
}

const REQUIRED_STEPS: FirstRunStep[] = ['connectProvider', 'oneClickTeam', 'projectFolder', 'firstTask'];

const OPTIONAL_STEPS: OptionalFirstRunStep[] = ['localAI', 'watcherPreset', 'automations', 'kbs'];

const FOLDER_PICK_URL = '/api/v1/sidecar/pick-folder';
const FOLDER_PICK_UNAVAILABLE = 409;

function folderLabel(key: string, fallback: string): string {
  try {
    return t(key);
  } catch {
    return fallback;
  }
}

async function requestFolderPick(): Promise<string | null> {
  const response = await requestResponse(FOLDER_PICK_URL, {
    method: 'POST',
    kind: 'write',
    body: {},
  });
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (typeof data === 'object' && data !== null) {
    const path = (data as { path?: unknown }).path;
    if (typeof path === 'string' && path.length > 0) {
      return path;
    }
  }
  return null;
}

interface StepError {
  errorKey: string;
  code: string;
}

function toStepError(error: unknown): StepError {
  if (error instanceof ApiError) {
    return { errorKey: apiErrorLocaleKey(error.code), code: error.code };
  }
  return { errorKey: 'errors.generic', code: 'CONTEXT_MISSING' };
}

function emptyError(): StepError {
  return { errorKey: 'errors.generic', code: 'CONTEXT_WRONG_CONTRACT_VERSION' };
}

// Optional context reads: bare unit mounts render FirstRunFlow with no
// providers, so the shared client/selection resolve to null there and the
// submit path below falls back to the legacy synchronous onComplete.
function useOptionalApiClient(): ApiClient | null {
  try {
    return useApiClient();
  } catch {
    return null;
  }
}

function useOptionalCurrentProject(): CurrentProject | null {
  try {
    return useCurrentProject();
  } catch {
    return null;
  }
}

export function FirstRunFlow(props: FirstRunFlowProps): ReactElement {
  const client = useOptionalApiClient();
  const selection = useOptionalCurrentProject();
  const inRouter = useInRouterContext();
  const [skipped, setSkipped] = useState<OptionalFirstRunStep[]>([]);
  const [index, setIndex] = useState<number>(() => {
    const at = REQUIRED_STEPS.indexOf(props.initialStep ?? 'connectProvider');
    return at < 0 ? 0 : at;
  });
  const [teamName, setTeamName] = useState<string>('');
  const [folder, setFolder] = useState<string>('');
  const [taskTitle, setTaskTitle] = useState<string>('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [teamProjectId, setTeamProjectId] = useState<string | null>(null);
  const [folderProjectId, setFolderProjectId] = useState<string | null>(null);
  const [teamBusy, setTeamBusy] = useState<boolean>(false);
  const [folderBusy, setFolderBusy] = useState<boolean>(false);
  const [taskBusy, setTaskBusy] = useState<boolean>(false);
  const [teamError, setTeamError] = useState<StepError | null>(null);
  const [folderError, setFolderError] = useState<StepError | null>(null);
  const [taskError, setTaskError] = useState<StepError | null>(null);
  const [created, setCreated] = useState<TaskRecord | null>(null);
  const [folderPickOpen, setFolderPickOpen] = useState<boolean>(true);
  const current: FirstRunStep = REQUIRED_STEPS[index] ?? 'connectProvider';
  const previous: FirstRunStep | undefined = index > 0 ? REQUIRED_STEPS[index - 1] : undefined;
  const skip = (step: OptionalFirstRunStep): void => {
    setSkipped((prev: OptionalFirstRunStep[]) => (prev.includes(step) ? prev : [...prev, step]));
  };
  const goNext = (): void => {
    setIndex((at: number) => Math.min(at + 1, REQUIRED_STEPS.length - 1));
  };
  const goBack = (): void => {
    setIndex((at: number) => Math.max(at - 1, 0));
  };
  const selectProject = (id: string): void => {
    if (selection !== null) {
      selection.select(id);
    }
    setProjectId(id);
  };
  // One-click team: ensure a project (list first, else create through the
  // real project API like ProjectsPage.submitAdd), then save the default
  // team role profiles through the real server path (saveRoleProfile PUTs).
  const handleOneClickTeam = async (): Promise<void> => {
    if (client === null || selection === null || teamBusy) {
      return;
    }
    const name = teamName.trim();
    if (name === '') {
      setTeamError(emptyError());
      return;
    }
    setTeamBusy(true);
    setTeamError(null);
    try {
      let pid = selection.projectId ?? projectId;
      if (pid === null) {
        const rows = await client.listProjects();
        const first = rows[0];
        if (first !== undefined) {
          pid = first.project_id;
          selectProject(pid);
        } else {
          const project = await client.createProject({ name, folder_ref: name });
          selectProject(project.project_id);
          pid = project.project_id;
        }
      }
      for (const role of ROLE_PROFILE_ROLES) {
        await saveRoleProfile(pid, { role, mode: 'AUTO' });
      }
      setTeamProjectId(pid);
    } catch (error) {
      setTeamError(toStepError(error));
    } finally {
      setTeamBusy(false);
    }
  };
  // Project folder: create the project through the real project API with
  // the folder value as both name and folder_ref (ChatStartBox pattern).
  const handleCreateProject = async (): Promise<void> => {
    if (client === null || selection === null || folderBusy) {
      return;
    }
    const folderRef = folder.trim();
    if (folderRef === '') {
      setFolderError(emptyError());
      return;
    }
    setFolderBusy(true);
    setFolderError(null);
    try {
      const project = await client.createProject({ name: folderRef, folder_ref: folderRef });
      selectProject(project.project_id);
      setFolderProjectId(project.project_id);
    } catch (error) {
      setFolderError(toStepError(error));
    } finally {
      setFolderBusy(false);
    }
  };
  // Folder picker: fill the folder input from the sidecar native dialog.
  // Cancel keeps the typed value; 409 (no native dialog) hides the control.
  const handleChooseFolder = async (): Promise<void> => {
    try {
      const picked = await requestFolderPick();
      if (picked !== null) {
        setFolder(picked);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === FOLDER_PICK_UNAVAILABLE) {
        setFolderPickOpen(false);
        return;
      }
      setFolderError(toStepError(error));
    }
  };
  // First task: without a provider this keeps the legacy synchronous
  // onComplete (bare unit mounts); with the shared client it posts through
  // the real task-API submit path (client.createTask) and only completes
  // from the Continue control once the served record renders.
  const submitTask = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (client === null || selection === null) {
      props.onComplete();
      return;
    }
    if (taskBusy) {
      return;
    }
    const title = taskTitle.trim();
    if (title === '') {
      setTaskError(emptyError());
      return;
    }
    setTaskBusy(true);
    setTaskError(null);
    void (async (): Promise<void> => {
      try {
        let pid = selection.projectId ?? projectId;
        if (pid === null) {
          const fallback = folder.trim() === '' ? title : folder.trim();
          const project = await client.createProject({ name: fallback, folder_ref: fallback });
          selectProject(project.project_id);
          pid = project.project_id;
        }
        const task = await client.createTask(pid, { title, scope: [] });
        setCreated(task);
      } catch (error) {
        setTaskError(toStepError(error));
      } finally {
        setTaskBusy(false);
      }
    })();
  };
  return (
    <section>
      <h2>{t('firstrun.title')}</h2>
      <ol>
        {REQUIRED_STEPS.map((step) => (
          <li
            key={step}
            aria-current={step === current ? 'step' : undefined}
            aria-label={t(`firstrun.steps.${step}`)}
          >
            {step === current ? (
              <h3>{t(`firstrun.steps.${step}`)}</h3>
            ) : (
              <span aria-hidden="true">{t(`firstrun.steps.${step}`)}</span>
            )}
          </li>
        ))}
      </ol>
      <section>
        {current === 'connectProvider' ? (
          <>
            <label>
              {t('settings.roleProfile.providerLabel')}
              <input
                type="text"
                aria-label={t('settings.roleProfile.providerLabel')}
                placeholder={t('chat.composer.prompt')}
              />
            </label>
            {inRouter ? (
              <Link to="/settings/models">{t('settings.models.title')}</Link>
            ) : (
              <a href="/settings/models">{t('settings.models.title')}</a>
            )}
          </>
        ) : null}
        {current === 'oneClickTeam' ? (
          <>
            <label>
              {t('shell.topbar.project')}
              <input
                type="text"
                aria-label={t('shell.topbar.project')}
                placeholder={t('shell.topbar.project')}
                value={teamName}
                onChange={(event) => {
                  setTeamName(event.target.value);
                }}
              />
            </label>
            <label>
              <input type="checkbox" aria-label={t('settings.roleProfile.modeLabel')} />
              {t('settings.roleProfile.modeLabel')}
            </label>
            <button
              type="button"
              disabled={teamBusy}
              onClick={() => {
                void handleOneClickTeam();
              }}
            >
              {t('settings.roleProfile.title')}
            </button>
            {teamProjectId !== null ? (
              <p data-testid="firstrun-team-result">{teamProjectId}</p>
            ) : null}
            {teamError !== null ? (
              <ErrorPanel errorKey={teamError.errorKey} code={teamError.code} onRetry={null} />
            ) : null}
          </>
        ) : null}
        {current === 'projectFolder' ? (
          <>
            <label>
              {t('settings.localbench.pathLabel')}
              <input
                type="text"
                aria-label={t('settings.localbench.pathLabel')}
                placeholder={t('settings.localbench.pathHint')}
                value={folder}
                onChange={(event) => {
                  setFolder(event.target.value);
                }}
              />
            </label>
            {folderPickOpen ? (
              <button
                type="button"
                data-testid="firstrun-folder-choose"
                onClick={() => {
                  void handleChooseFolder();
                }}
              >
                {folderLabel('firstrun.folder.choose', 'Choose folder')}
              </button>
            ) : null}
            <button
              type="button"
              disabled={folderBusy}
              onClick={() => {
                void handleCreateProject();
              }}
            >
              {t('tasks.creator.create')}
            </button>
            {folderProjectId !== null ? (
              <p data-testid="firstrun-project-result">{folderProjectId}</p>
            ) : null}
            {folderError !== null ? (
              <ErrorPanel errorKey={folderError.errorKey} code={folderError.code} onRetry={null} />
            ) : null}
          </>
        ) : null}
        {current === 'firstTask' ? (
          <form onSubmit={submitTask}>
            <h4>{t('tasks.creator.title')}</h4>
            <label>
              {t('tasks.creator.title')}
              <input
                type="text"
                value={taskTitle}
                onChange={(event) => setTaskTitle(event.target.value)}
              />
            </label>
            <button type="submit" disabled={taskBusy}>{t('tasks.creator.create')}</button>
            {taskError !== null ? (
              <ErrorPanel errorKey={taskError.errorKey} code={taskError.code} onRetry={null} />
            ) : null}
            {created !== null ? (
              <div>
                <p data-testid="firstrun-task-result">{created.title}</p>
                <button
                  type="button"
                  onClick={() => {
                    props.onComplete();
                  }}
                >
                  {t('shell.sidebar.chat')}
                </button>
              </div>
            ) : null}
          </form>
        ) : (
          <>
            {previous === undefined ? null : (
              <button type="button" onClick={goBack}>
                {t(`firstrun.steps.${previous}`)}
              </button>
            )}
            <button type="button" onClick={goNext}>
              {t('firstrun.next')}
            </button>
          </>
        )}
      </section>
      <p>{t('firstrun.optionalNote')}</p>
      <ul>
        {OPTIONAL_STEPS.map((step) => (
          <li key={step}>
            {t(`firstrun.optional.${step}`)}
            {skipped.includes(step) ? null : (
              <button type="button" onClick={() => skip(step)}>
                {t('firstrun.skip')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
