// FXFIRSTRUN2 focused first-run page: a 640-wide card, a 4-step progress
// line, provider rows with the real connect modal, one-click team, the real
// folder picker, the first-message box, and one quiet optional list on the
// last step. Connected state always comes from served data (GET
// /api/v1/providers); nothing is marked done unless the server says so.
// Bare unit mounts (no ApiClientProvider above) keep the legacy synchronous
// walk so unit tests never touch the network.
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactElement } from 'react';
import './firstrun.css';
import { t } from '../../locale/index';
import { ApiError, apiErrorLocaleKey, getUiToken, requestResponse } from '../../api/errors';
import type { ApiClient, TaskRecord } from '../../api/iface';
import { useApiClient, useCurrentProject } from '../ApiClientProvider';
import type { CurrentProject } from '../ApiClientProvider';
import { saveRoleProfile } from '../../settings/index';
import { ROLE_PROFILE_ROLES } from '../../settings/roleProfilesApi';
import { ErrorPanel } from '../../ui/ErrorPanel';
import { PROVIDER_CATALOG, getPreset } from '../../settings/ProvidersPage/catalog';
import { listConnectedProviders } from '../../settings/ProvidersPage/connectApi';
import { ConnectDialog } from '../../settings/ProvidersPage/ConnectDialog';
import { DisconnectDialog } from '../../settings/ProvidersPage/DisconnectDialog';
import { createMemorySecretStore, secretIdForProvider } from '../../settings/ProvidersPage/secretStore';
import type { SecretStorePort } from '../../settings/ProvidersPage/secretStore';
import { roleLabel } from '../../settings/ProvidersPage/types';

export type FirstRunStep = 'connectProvider' | 'oneClickTeam' | 'projectFolder' | 'firstTask';

export type OptionalFirstRunStep = 'localAI' | 'watcherPreset' | 'automations' | 'kbs';

export interface FirstRunFlowProps {
  initialStep?: FirstRunStep;
  onComplete: () => void;
}

const REQUIRED_STEPS: FirstRunStep[] = ['connectProvider', 'oneClickTeam', 'projectFolder', 'firstTask'];

const OPTIONAL_STEPS: OptionalFirstRunStep[] = ['localAI', 'watcherPreset', 'automations', 'kbs'];

// Juror-first-30-seconds rows: the two biggest clouds, Anthropic, and local.
const FIRST_RUN_PRESET_IDS = ['meta', 'openai', 'anthropic', 'ollama'];

const FOLDER_PICK_URL = '/api/v1/sidecar/pick-folder';
const FOLDER_PICK_UNAVAILABLE = 409;

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

function validationError(errorKey: string): StepError {
  // FXFIRST: empty required fields are honest client-side validation, never
  // a fabricated contract code (the H73 raw-enum report). The code below
  // is StepError-local and renders behind Details only, never as text.
  return { errorKey, code: 'VALIDATION_REQUIRED' };
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
  const served = client !== null && selection !== null;
  const [storeInstance] = useState<SecretStorePort>(() => createMemorySecretStore(getUiToken() ?? ''));
  const presets = useMemo(
    () =>
      FIRST_RUN_PRESET_IDS.map((id) => getPreset(PROVIDER_CATALOG, id)).filter(
        (preset) => preset !== undefined,
      ),
    [],
  );
  // Served connected ids; null until the first GET answers. The Next gate
  // and every row badge read this, never localStorage.
  const [connectedIds, setConnectedIds] = useState<string[] | null>(null);
  const [connectId, setConnectId] = useState<string | null>(null);
  const [disconnectId, setDisconnectId] = useState<string | null>(null);
  const [providerSkipped, setProviderSkipped] = useState<boolean>(false);
  const refreshConnected = useCallback((): void => {
    if (!served || client === null) {
      return;
    }
    void listConnectedProviders().then((ids) => {
      setConnectedIds(ids);
    });
  }, [served, client]);
  useEffect(() => {
    refreshConnected();
  }, [refreshConnected]);
  const hasConnected = (connectedIds ?? []).length > 0;
  const [skipped, setSkipped] = useState<OptionalFirstRunStep[]>([]);
  const [index, setIndex] = useState<number>(() => {
    const at = REQUIRED_STEPS.indexOf(props.initialStep ?? 'connectProvider');
    return at < 0 ? 0 : at;
  });
  const [teamName, setTeamName] = useState<string>('');
  const [folder, setFolder] = useState<string>('');
  const [taskTitle, setTaskTitle] = useState<string>('');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [teamResult, setTeamResult] = useState<{ name: string; projectId: string } | null>(null);
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
  const providerGate = current === 'connectProvider' && served && !hasConnected && !providerSkipped;
  // FXFIRST item 4: one-click team with no provider is disabled with the
  // reason on screen plus a link to step 1. Skipping step 1 is an explicit
  // providerless choice, so the gate lifts for skipped runs (the server
  // decides the team write); bare unit mounts (not served) keep the legacy
  // enabled button.
  const teamBlocked = served && !hasConnected && !providerSkipped;
  const goNext = (): void => {
    if (providerGate) {
      return;
    }
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
      setTeamError(validationError('firstrun.team.nameRequired'));
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
      setTeamResult({ name, projectId: pid });
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
      setFolderError(validationError('firstrun.folder.required'));
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
      setTaskError(validationError('tasks.creator.titleRequired'));
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
  const connectPreset = connectId === null ? null : (presets.find((p) => p.id === connectId) ?? null);
  const disconnectPreset =
    disconnectId === null ? null : (presets.find((p) => p.id === disconnectId) ?? null);
  const teamRolesLine =
    teamResult === null
      ? null
      : ROLE_PROFILE_ROLES.map((role) => roleLabel(role)).join(', ') +
        `: ${t('providers.rolepool.modeAuto')}`;
  return (
    <section data-testid="firstrun" className="fx-firstrun">
      <h2>{t('firstrun.title')}</h2>
      <ol className="fx-firstrun-steps">
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
      <section className="fx-firstrun-card">
        {current === 'connectProvider' ? (
          <>
            <ul className="fx-firstrun-providers">
              {presets.map((preset) => {
                const connected = (connectedIds ?? []).includes(preset.id);
                return (
                  <li
                    key={preset.id}
                    data-testid={`firstrun-provider-${preset.id}`}
                    className="fx-firstrun-provider"
                  >
                    <h4>{preset.label}</h4>
                    <p>
                      {connected
                        ? t('providers.connect.connected', { label: preset.label })
                        : preset.kind === 'local'
                          ? t('firstrun.provider.localNote')
                          : t('providers.connect.getKey', { label: preset.label })}
                    </p>
                    {connected ? (
                      <button
                        type="button"
                        className="fx-btn-quiet"
                        aria-label={t('providers.page.disconnectCta', { label: preset.label })}
                        onClick={() => setDisconnectId(preset.id)}
                      >
                        {t('providers.page.disconnectLabel')}
                      </button>
                    ) : (
                      <button
                        type="button"
                        aria-label={t('providers.page.connectCta', { label: preset.label })}
                        onClick={() => setConnectId(preset.id)}
                      >
                        {t('providers.page.connectLabel')}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            <ConnectDialog
              preset_id={connectId ?? ''}
              preset={connectPreset}
              open={connectId !== null}
              store={storeInstance}
              onClose={() => setConnectId(null)}
              onConnected={() => {
                setConnectId(null);
                refreshConnected();
              }}
            />
            <DisconnectDialog
              provider_id={disconnectId ?? ''}
              providerLabel={disconnectPreset?.label ?? ''}
              secretId={disconnectId === null ? '' : secretIdForProvider(disconnectId)}
              open={disconnectId !== null}
              store={storeInstance}
              sessionToken={getUiToken() ?? ''}
              onClose={() => setDisconnectId(null)}
              onDisconnected={() => {
                setDisconnectId(null);
                refreshConnected();
              }}
            />
          </>
        ) : null}
        {current === 'oneClickTeam' ? (
          <>
            <p data-testid="firstrun-team-mode-hint">{t('providers.setup.hint')}</p>
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
            <button
              type="button"
              disabled={teamBusy || teamBlocked}
              onClick={() => {
                void handleOneClickTeam();
              }}
            >
              {t('settings.roleProfile.title')}
            </button>
            {teamBlocked ? (
              <>
                <p data-testid="firstrun-team-need-provider">{t('firstrun.team.needProvider')}</p>
                <button
                  type="button"
                  className="fx-btn-quiet"
                  data-testid="firstrun-team-back"
                  onClick={() => {
                    setIndex(0);
                  }}
                >
                  {t('firstrun.steps.connectProvider')}
                </button>
              </>
            ) : null}
            {teamResult !== null ? (
              <p data-testid="firstrun-team-result">
                {teamResult.name} · {teamResult.projectId} · {teamRolesLine}
              </p>
            ) : null}
            {teamError !== null ? (
              <ErrorPanel errorKey={teamError.errorKey} code={teamError.code} onRetry={null} />
            ) : null}
          </>
        ) : null}
        {current === 'projectFolder' ? (
          <>
            <label>
              {t('firstrun.folder.label')}
              <input
                type="text"
                aria-label={t('firstrun.folder.label')}
                placeholder={t('firstrun.folder.hint')}
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
                {t('firstrun.folder.choose')}
              </button>
            ) : null}
            <button
              type="button"
              disabled={folderBusy}
              onClick={() => {
                void handleCreateProject();
              }}
            >
              {t('projects.list.create')}
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
              <button type="button" className="fx-btn-quiet" onClick={goBack}>
                {t('firstrun.back')}
              </button>
            )}
            <button type="button" disabled={providerGate} onClick={goNext}>
              {t('firstrun.next')}
            </button>
            {current === 'connectProvider' ? (
              <button
                type="button"
                className="fx-btn-quiet"
                onClick={() => {
                  setProviderSkipped(true);
                  setIndex((at: number) => Math.min(at + 1, REQUIRED_STEPS.length - 1));
                }}
              >
                {t('firstrun.skip')}
              </button>
            ) : null}
          </>
        )}
      </section>
      {current === 'firstTask' ? (
        <section className="fx-firstrun-optional" aria-label={t('firstrun.optionalNote')}>
          <p>{t('firstrun.optionalNote')}</p>
          <ul>
            {OPTIONAL_STEPS.map((step) => (
              <li key={step}>
                {t(`firstrun.optional.${step}`)}
                {skipped.includes(step) ? null : (
                  <button type="button" className="fx-btn-quiet" onClick={() => skip(step)}>
                    {t('firstrun.skip')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
