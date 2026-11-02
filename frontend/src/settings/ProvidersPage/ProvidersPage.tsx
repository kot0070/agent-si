// Providers settings page: stable-order provider list with groups,
// a search box on top, per-model checkboxes, connect/disconnect dialogs,
// a chat picker (enabled models only) and the leftover-key finder.

import { useCallback, useEffect, useMemo, useState } from "react";
import { getUiToken } from "../../api/errors";
import { deleteLeftoverKey, listConnectedProviders, listLeftoverKeys } from "./connectApi";
import { PROVIDER_CATALOG } from "./catalog";
import { ChatModelSelector } from "./ChatModelSelector";
import { enabledChatChoices } from "./ChatSelector";
import { ConnectDialog } from "./ConnectDialog";
import { DisconnectDialog } from "./DisconnectDialog";
import { LeftoverKeyFinder } from "./LeftoverKeyFinder";
import { RolePoolPicker, choicesToPoolOptions } from "./RolePoolPicker";
import type { RolePoolValue } from "./RolePoolPicker";
import { SetupWizard } from "./SetupWizard";
import { saveRolePool } from "./poolsApi";
import { createMemorySecretStore, secretIdForProvider } from "./secretStore";
import type { SecretStorePort } from "./secretStore";
import { APP_NAMESPACE_PREFIX, ROLE_KEYS, roleLabel } from "./types";
import type { ProviderPreset, ProviderState, SecretRef } from "./types";
import { t } from "../../locale/index";

// Save helper for the project chat model.
// PUTs {project_id, model_id} to /api/v1/roles/chat-model with the session
// token in the x-ui-session-token header (never in the URL or the JSON body).
export async function saveChatModel(
  project_id: string,
  model_id: string,
  sessionToken: string,
): Promise<void> {
  const response = await fetch("/api/v1/roles/chat-model", {
    method: "PUT",
    headers: { "Content-Type": "application/json", "x-ui-session-token": sessionToken },
    body: JSON.stringify({ project_id, model_id }),
  });
  if (!response.ok) {
    throw new Error(t("providers.page.chatSaveError", { status: String(response.status) }));
  }
}

type ProvidersPageProps = {
  project_id?: string;
};

function initialStates(catalog: ProviderPreset[]): Record<string, ProviderState> {
  const out: Record<string, ProviderState> = {};
  for (const preset of catalog) {
    out[preset.id] = { presetId: preset.id, connected: false, enabledModels: [] };
  }
  return out;
}

export function ProvidersPage({ project_id = "local" }: ProvidersPageProps) {
  const catalog = PROVIDER_CATALOG;
  // The window's real session token: this page reads it and never replaces it.
  const sessionToken = getUiToken() ?? "";
  const project = project_id;
  const [storeInstance] = useState<SecretStorePort>(() => createMemorySecretStore(sessionToken));
  const [states, setStates] = useState<Record<string, ProviderState>>(() => initialStates(catalog));
  const [query, setQuery] = useState("");
  const [connectId, setConnectId] = useState<string | null>(null);
  const [disconnectId, setDisconnectId] = useState<string | null>(null);
  const [finderKey, setFinderKey] = useState(0);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardDone, setWizardDone] = useState(false);

  // Cards state on open: a background GET marks the providers the routes
  // already know as connected. It never throws and never disturbs the page
  // when no route answers.
  useEffect(() => {
    let cancelled = false;
    void listConnectedProviders().then((ids) => {
      if (cancelled || ids.length === 0) {
        return;
      }
      const known = new Set(ids);
      setStates((prev) => {
        const next: Record<string, ProviderState> = { ...prev };
        for (const id of Object.keys(next)) {
          if (known.has(id)) {
            const current = next[id] as ProviderState;
            next[id] = { ...current, connected: true };
          }
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Stable order: the catalog array order, captured once. Never re-sorted,
  // so connecting, toggling or refreshing never reorders or flickers rows.
  const ordered = useMemo(() => catalog.slice(), [catalog]);

  const groups = useMemo(() => {
    const names: string[] = [];
    for (const preset of ordered) {
      if (!names.includes(preset.group)) {
        names.push(preset.group);
      }
    }
    return names.map((name) => ({
      name,
      presets: ordered.filter((preset) => preset.group === name),
    }));
  }, [ordered]);

  const choices = useMemo(() => enabledChatChoices(ordered, states), [ordered, states]);
  const poolOptions = useMemo(() => choicesToPoolOptions(choices), [choices]);
  const [poolSaveMessage, setPoolSaveMessage] = useState("");
  const [chatSaveMessage, setChatSaveMessage] = useState("");
  const needle = query.trim().toLowerCase();

  async function handleRolePoolChange(role: string, value: RolePoolValue): Promise<void> {
    try {
      await saveRolePool(project, role, value, poolOptions);
      setPoolSaveMessage(t("providers.page.poolSaved", { role: roleLabel(role) }));
    } catch {
      setPoolSaveMessage(t("providers.page.poolSaveFailed", { role: roleLabel(role) }));
    }
  }

  async function handleChatModelChange(modelId: string): Promise<void> {
    try {
      await saveChatModel(project, modelId, sessionToken);
      setChatSaveMessage(t("providers.page.chatSaved"));
    } catch {
      setChatSaveMessage(t("providers.page.chatSaveFailed"));
    }
  }

  function visible(preset: ProviderPreset): boolean {
    if (needle.length === 0) {
      return true;
    }
    if (preset.label.toLowerCase().includes(needle)) {
      return true;
    }
    return preset.models.some((model) => model.label.toLowerCase().includes(needle));
  }

  function toggleModel(presetId: string, modelId: string): void {
    setStates((prev) => {
      const current = prev[presetId];
      if (!current || !current.connected) {
        return prev;
      }
      const on = current.enabledModels.includes(modelId);
      return {
        ...prev,
        [presetId]: {
          ...current,
          enabledModels: on
            ? current.enabledModels.filter((id) => id !== modelId)
            : [...current.enabledModels, modelId],
        },
      };
    });
  }

  function handleConnected(presetId: string): void {
    setStates((prev) => ({
      ...prev,
      [presetId]: { ...(prev[presetId] as ProviderState), presetId, connected: true },
    }));
    setFinderKey((key) => key + 1);
  }

  function handleDisconnected(secretId: string): void {
    setStates((prev) => {
      const next: Record<string, ProviderState> = { ...prev };
      for (const id of Object.keys(next)) {
        if (secretIdForProvider(id) === secretId) {
          next[id] = { ...(next[id] as ProviderState), connected: false, enabledModels: [] };
        }
      }
      return next;
    });
    setDisconnectId(null);
    setFinderKey((key) => key + 1);
  }

  function handleWizardDone(): void {
    setWizardDone(true);
  }

  const connectPreset = connectId === null ? null : (ordered.find((p) => p.id === connectId) ?? null);
  const disconnectPreset =
    disconnectId === null ? null : (ordered.find((p) => p.id === disconnectId) ?? null);
  const linkedSecretIds = ordered
    .filter((preset) => states[preset.id]?.connected === true)
    .map((preset) => secretIdForProvider(preset.id));

  // Leftover keys come from the real leftover-keys route (names plus
  // dates only) and deletes go to the real leftover-delete route with
  // a per-entry confirm plus the session token. Both callbacks stay
  // stable so the finder never refetches in a loop; the token is read
  // late, so a login that completes after mount still deletes.
  const loadLeftoverEntries = useCallback(
    (): Promise<SecretRef[]> => listLeftoverKeys(APP_NAMESPACE_PREFIX),
    [],
  );
  const deleteLeftoverEntry = useCallback(
    (entry: SecretRef): Promise<void> =>
      deleteLeftoverKey(APP_NAMESPACE_PREFIX, entry.secret_id, getUiToken() ?? ""),
    [],
  );

  return (
    <div>
      <h1>{t("providers.page.title")}</h1>
      <label>
        {t("providers.page.searchLabel")}
        <input
          type="search"
          aria-label={t("providers.page.searchLabel")}
          value={query}
          placeholder={t("settings.providers.searchPlaceholder")}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      {groups.map((group) => {
        const shown = group.presets.filter(visible);
        if (shown.length === 0) {
          return null;
        }
        return (
          <section key={group.name} aria-label={group.name}>
            <h2>{group.name}</h2>
            {shown.map((preset) => {
              const state = states[preset.id] ?? {
                presetId: preset.id,
                connected: false,
                enabledModels: [],
              };
              return (
                <article key={preset.id} data-testid="provider-card" data-provider-id={preset.id}>
                  <h3>{preset.label}</h3>
                  {state.connected ? (
                    <button
                      type="button"
                      aria-label={t("providers.page.disconnectCta", { label: preset.label })}
                      onClick={() => setDisconnectId(preset.id)}
                    >
                      {t("providers.page.disconnectLabel")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      aria-label={t("providers.page.connectCta", { label: preset.label })}
                      onClick={() => setConnectId(preset.id)}
                    >
                      {t("providers.page.connectLabel")}
                    </button>
                  )}
                  <p
                    data-testid={`provider-caps-${preset.id}`}
                    className="fx-cap-line"
                    title={preset.caps ?? t("shell.common.unknown")}
                  >
                    {preset.caps ?? "—"}
                  </p>
                  <p data-testid={`provider-keynote-${preset.id}`} className="fx-quiet-line">
                    {preset.keyHint}
                  </p>
                  <ul>
                    {preset.models.map((model) => (
                      <li key={model.id} data-testid="model-row">
                        <label>
                          <input
                            type="checkbox"
                            aria-label={`${preset.label} ${model.label}`}
                            title={
                              state.connected
                                ? undefined
                                : t("chat.hierarchy.connect")
                            }
                            checked={state.enabledModels.includes(model.id)}
                            disabled={!state.connected}
                            onChange={() => toggleModel(preset.id, model.id)}
                          />
                          {model.label}
                        </label>{" "}
                        <small data-testid={`model-id-${model.id}`}>
                          {model.id}
                        </small>
                      </li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </section>
        );
      })}
      <section aria-label={t("providers.page.setupTitle")}>
        <h2>{t("providers.page.setupTitle")}</h2>
        <button
          type="button"
          aria-expanded={showWizard}
          onClick={() => setShowWizard((open) => !open)}
        >
          {showWizard ? t("providers.page.setupHide") : t("providers.page.setupShow")}
        </button>
        {showWizard ? (
          <div>
            <SetupWizard choices={choices} onDone={handleWizardDone} />
            {wizardDone ? <p role="status">{t("providers.page.setupSaved")}</p> : null}
          </div>
        ) : null}
      </section>
      <section aria-label={t("providers.page.rolePoolsTitle")}>
        <h2>{t("providers.page.rolePoolsTitle")}</h2>
        {ROLE_KEYS.map((role) => (
          <RolePoolPicker
            key={role}
            role={role}
            project_id={project}
            options={poolOptions}
            onChange={(value) => void handleRolePoolChange(role, value)}
          />
        ))}
        {poolSaveMessage ? <p role="status">{poolSaveMessage}</p> : null}
      </section>
      <section aria-label={t("providers.page.chatTitle")}>
        <h2>{t("providers.page.chatTitle")}</h2>
        <ChatModelSelector
          project_id={project}
          states={states}
          onChange={(modelId) => void handleChatModelChange(modelId)}
        />
        {chatSaveMessage ? <p role="status">{chatSaveMessage}</p> : null}
      </section>
      <section aria-label={t("providers.page.leftoverTitle")}>
        <h2>{t("providers.page.leftoverTitle")}</h2>
        <LeftoverKeyFinder
          store={storeInstance}
          sessionToken={sessionToken}
          linkedSecretIds={linkedSecretIds}
          refreshKey={finderKey}
          loadEntries={loadLeftoverEntries}
          deleteEntry={deleteLeftoverEntry}
        />
      </section>
      <ConnectDialog
        preset_id={connectId ?? ""}
        preset={connectPreset}
        open={connectId !== null}
        store={storeInstance}
        onClose={() => setConnectId(null)}
        onConnected={handleConnected}
      />
      <DisconnectDialog
        provider_id={disconnectId ?? ""}
        providerLabel={disconnectPreset?.label ?? ""}
        secretId={disconnectId === null ? "" : secretIdForProvider(disconnectId)}
        open={disconnectId !== null}
        store={storeInstance}
        sessionToken={sessionToken}
        onClose={() => setDisconnectId(null)}
        onDisconnected={handleDisconnected}
      />
    </div>
  );
}
