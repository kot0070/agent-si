// Providers settings page: stable-order provider list with groups,
// a search box on top, per-model checkboxes, connect/disconnect dialogs,
// a chat picker (enabled models only) and the leftover-key finder.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getUiToken } from "../../api/errors";
import { deleteLeftoverKey, listConnectedProviders, listLeftoverKeys } from "./connectApi";
import { listServedModels, mergeModelList, modelPriceText } from "./modelsApi";
import type { ServedModelRow } from "./modelsApi";
import { getProviderCatalog } from "./catalog";
import { ChatModelSelector } from "./ChatModelSelector";
import { buildRoleChoices } from "./roleChoices";
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
  // Locale-current catalog: display strings (group, keyHint, model labels)
  // resolve through t() for the active locale on every render.
  const catalog = useMemo(() => getProviderCatalog(), []);
  // The window's real session token: this page reads it and never replaces it.
  const sessionToken = getUiToken() ?? "";
  const project = project_id;
  const [storeInstance] = useState<SecretStorePort>(() => createMemorySecretStore(sessionToken));
  const [states, setStates] = useState<Record<string, ProviderState>>(() => initialStates(catalog));
  const [query, setQuery] = useState("");
  const [connectId, setConnectId] = useState<string | null>(null);
  const [disconnectId, setDisconnectId] = useState<string | null>(null);
  const [finderKey, setFinderKey] = useState(0);
  // Step-2 Manage models: reopens the same dialog at the model list with
  // the current ticks (no key asked twice).
  const [manageId, setManageId] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardDone, setWizardDone] = useState(false);
  // Last provider connected through the dialog: its card carries the quiet
  // "Connected {label}." line next to Disconnect.
  const [lastConnectedId, setLastConnectedId] = useState<string | null>(null);
  // Served model listings per preset (GET /api/v1/providers/{id}/models):
  // the provider's own rows the routes know, merged over the KB catalog.
  const [servedModels, setServedModels] = useState<Record<string, ServedModelRow[]>>({});

  // Served state is the truth: mark the providers the routes already know
  // as connected (union only, never clears local picks on a partial read).
  // It never throws and never disturbs the page when no route answers.
  async function refreshConnected(): Promise<void> {
    const ids = await listConnectedProviders();
    if (ids.length === 0) {
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
  }

  // Served model listings for the given presets (never throws).
  async function loadServedModels(presetIds: string[]): Promise<void> {
    if (presetIds.length === 0) {
      return;
    }
    const entries = await Promise.all(
      presetIds.map(async (id) => ({ id, rows: await listServedModels(id) })),
    );
    setServedModels((prev) => {
      const next: Record<string, ServedModelRow[]> = { ...prev };
      for (const entry of entries) {
        next[entry.id] = entry.rows;
      }
      return next;
    });
  }

  // Cards state on open: a background GET marks the providers the routes
  // already know as connected, then their served model listings merge in.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const ids = await listConnectedProviders();
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
      const entries = await Promise.all(
        ids.map(async (id) => ({ id, rows: await listServedModels(id) })),
      );
      if (cancelled) {
        return;
      }
      setServedModels((prev) => {
        const next: Record<string, ServedModelRow[]> = { ...prev };
        for (const entry of entries) {
          next[entry.id] = entry.rows;
        }
        return next;
      });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Display models per preset: the served provider listing (the rows the
  // routes know for this provider) first, then the KB-derived catalog
  // entries not already listed. Role pickers, the chat picker and search
  // all read this same merged list; nothing outside these two sources.
  const displayModels = useMemo(() => {
    const out: Record<string, Array<{ id: string; label: string; kb: unknown }>> = {};
    for (const preset of catalog) {
      out[preset.id] = mergeModelList(preset.models, servedModels[preset.id] ?? [], preset.id);
    }
    return out;
  }, [catalog, servedModels]);

  // Same merged list in catalog shape for the pickers (chat, roles, setup).
  const displayCatalog = useMemo(
    () =>
      catalog.map((preset) => ({
        ...preset,
        models: (displayModels[preset.id] ?? []).map((model) => ({
          id: model.id,
          label: model.label,
          kb: model.kb,
        })),
      })),
    [catalog, displayModels],
  );

  // Stable order: the catalog array order, captured once. Never re-sorted,
  // so connecting, toggling or refreshing never reorders or flickers rows.
  // Groups follow the merged catalog so cards and pickers share one order.
  const groups = useMemo(() => {
    const names: string[] = [];
    for (const preset of displayCatalog) {
      if (!names.includes(preset.group)) {
        names.push(preset.group);
      }
    }
    return names.map((name) => ({
      name,
      presets: displayCatalog.filter((preset) => preset.group === name),
    }));
  }, [displayCatalog]);

  // R1: role/wizard/chat options: connected providers, then each
  // provider instance's model list — the enabled models as full
  // `provider/model` ids (placeholders, `unknown` and KB-proven
  // non-text rows never reach the list).
  const choices = useMemo(
    () => buildRoleChoices(displayCatalog, displayModels, states),
    [displayCatalog, displayModels, states],
  );
  const poolOptions = useMemo(() => choicesToPoolOptions(choices), [choices]);
  const [poolSaveMessage, setPoolSaveMessage] = useState("");
  const [chatSaveMessage, setChatSaveMessage] = useState("");
  const needle = query.trim().toLowerCase();

  // R1: a save refusal names the server's own reason in one
  // sentence (the generic line alone never ships).
  function saveFailure(base: string, err: unknown): string {
    if (err instanceof ApiError) {
      const reason = err.details?.message;
      if (typeof reason === "string" && reason.trim() !== "") {
        return `${base}: ${reason.trim()}`;
      }
    } else if (err instanceof Error && err.message.trim() !== "") {
      return `${base}: ${err.message.trim()}`;
    }
    return base;
  }

  async function handleRolePoolChange(role: string, value: RolePoolValue): Promise<void> {
    try {
      await saveRolePool(project, role, value, poolOptions);
      setPoolSaveMessage(t("providers.page.poolSaved", { role: roleLabel(role) }));
    } catch (err) {
      setPoolSaveMessage(
        saveFailure(t("providers.page.poolSaveFailed", { role: roleLabel(role) }), err),
      );
    }
  }

  async function handleChatModelChange(modelId: string): Promise<void> {
    try {
      await saveChatModel(project, modelId, sessionToken);
      setChatSaveMessage(t("providers.page.chatSaved"));
    } catch (err) {
      setChatSaveMessage(
        saveFailure(t("providers.page.chatSaveFailed"), err),
      );
    }
  }

  function visible(preset: ProviderPreset): boolean {
    if (needle.length === 0) {
      return true;
    }
    if (preset.label.toLowerCase().includes(needle)) {
      return true;
    }
    const models = displayModels[preset.id] ?? preset.models;
    return models.some(
      (model) =>
        model.label.toLowerCase().includes(needle) ||
        model.id.toLowerCase().includes(needle),
    );
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
    // Fresh connect ticks only the default model (the connect id): never
    // everything, even when the account lists 100+ models. Local presets
    // are served-driven (the runtime's real names): nothing is ticked
    // up front, the seeded list offers them instead.
    const preset = catalog.find((entry) => entry.id === presetId);
    const defaultId = preset?.kind === "local"
      ? undefined
      : preset?.models[0]?.id;
    setStates((prev) => {
      const current = prev[presetId] as ProviderState | undefined;
      const enabled = current !== undefined && current.enabledModels.length > 0
        ? current.enabledModels
        : defaultId === undefined
          ? []
          : [defaultId];
      return {
        ...prev,
        [presetId]: {
          ...(current ?? { presetId, connected: false, enabledModels: [] }),
          presetId,
          connected: true,
          enabledModels: enabled,
        },
      };
    });
    // The dialog stays open and moves to step 2 itself; the card keeps a
    // quiet Connected line. Served state re-validates in the background.
    setLastConnectedId(presetId);
    setFinderKey((key) => key + 1);
    void loadServedModels([presetId]);
    void refreshConnected();
  }

  // Done in step 2 (or Manage models) commits the ticked ids for the card,
  // the chat picker, Auto and the role pickers. The dialog PUTs the ticks
  // to the provider-models write route first, so the server's enabled
  // list (the routing truth) already holds them; the card mirrors them.
  function handleModelsDone(presetId: string, modelIds: string[]): void {
    setStates((prev) => ({
      ...prev,
      [presetId]: { ...(prev[presetId] as ProviderState), presetId, connected: true, enabledModels: modelIds },
    }));
    setManageId(null);
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
    setLastConnectedId((prev) =>
      prev !== null && secretIdForProvider(prev) === secretId ? null : prev,
    );
    setFinderKey((key) => key + 1);
    // Served re-read after disconnect: the route no longer lists the
    // provider, so the union refresh keeps the card disconnected.
    void refreshConnected();
  }

  function handleWizardDone(): void {
    setWizardDone(true);
  }

  const dialogId = connectId ?? manageId;
  const connectPreset = dialogId === null ? null : (catalog.find((p) => p.id === dialogId) ?? null);
  const disconnectPreset =
    disconnectId === null ? null : (catalog.find((p) => p.id === disconnectId) ?? null);
  const linkedSecretIds = catalog
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
                    <>
                      <button
                        type="button"
                        aria-label={t("providers.page.disconnectCta", { label: preset.label })}
                        onClick={() => setDisconnectId(preset.id)}
                      >
                        {t("providers.page.disconnectLabel")}
                      </button>
                      <button
                        type="button"
                        aria-label={t("providers.page.manageModelsCta", { label: preset.label })}
                        onClick={() => setManageId(preset.id)}
                      >
                        {t("providers.page.manageModels")}
                      </button>
                      <p data-testid={`provider-enabled-${preset.id}`} data-variant="quiet">
                        {state.enabledModels.length === 0
                          ? t("providers.page.noneEnabled")
                          : t("providers.page.enabledCount", { count: String(state.enabledModels.length) })}
                      </p>
                      {lastConnectedId === preset.id ? (
                        <p role="status" data-variant="quiet">
                          {t("providers.connect.connected", { label: preset.label })}
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <>
                    <button
                      type="button"
                      aria-label={t("providers.page.connectCta", { label: preset.label })}
                      onClick={() => setConnectId(preset.id)}
                    >
                      {t("providers.page.connectLabel")}
                    </button>
                    {preset.kind === "local" ? null : (
                      <p
                        data-testid={`provider-getkey-${preset.id}`}
                        className="fx-quiet-line"
                      >
                        {t("providers.connect.getKey", { label: preset.label })}
                      </p>
                    )}
                    </>
                  )}
                  <p data-testid={`provider-keynote-${preset.id}`} className="fx-quiet-line">
                    {preset.keyHint}
                  </p>
                  <ul>
                    {(displayModels[preset.id] ?? []).map((model) => (
                      <li key={model.id} data-testid="model-row">
                        {model.label === model.id ? null : (
                          <>
                            <span>{model.label}</span>{" "}
                          </>
                        )}
                        <small data-testid={`model-id-${model.id}`} title={model.id}>
                          {model.id}
                        </small>{" "}
                        <span data-testid={`model-price-${model.id}`}>
                          {modelPriceText(model.kb)}
                        </span>{" "}
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
          catalog={displayCatalog}
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
        preset_id={dialogId ?? ""}
        preset={connectPreset}
        open={dialogId !== null}
        store={storeInstance}
        initialStep={manageId !== null ? 2 : 1}
        initialTicked={
          manageId !== null ? (states[manageId]?.enabledModels ?? []) : undefined
        }
        onClose={() => {
          setConnectId(null);
          setManageId(null);
        }}
        onConnected={handleConnected}
        onModelsDone={handleModelsDone}
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
