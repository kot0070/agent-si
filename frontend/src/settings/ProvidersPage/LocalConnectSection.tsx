// Local presets connect block for Settings -> Local LLM (the localAI route).
// One row per kind-local preset (Ollama, LM Studio): label, base URL, served
// connected state, and the SAME ConnectDialog / DisconnectDialog the Providers
// page uses, so both pages share one served truth (listConnectedProviders) and
// one dialog flow. The stored bench panel stays below this block in App.tsx.
// A preset whose probe finds no server shows the existing localNotRunning
// sentence; an empty catalog shows one sentence telling what to do.

import { useEffect, useMemo, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, getUiToken } from "../../api/errors";
import { listConnectedProviders, probeLocalModels } from "./connectApi";
import { getProviderCatalog } from "./catalog";
import { ConnectDialog } from "./ConnectDialog";
import { DisconnectDialog } from "./DisconnectDialog";
import { createMemorySecretStore, secretIdForProvider } from "./secretStore";
import type { SecretStorePort } from "./secretStore";
import type { ProviderPreset } from "./types";
import { listProviderModels } from "./modelsApi";
import type { ProviderModelRow } from "./modelsApi";
import { AGENT_ROLES, readRolePools, saveRolePool } from "./poolsApi";
import type { RolePoolReadRow } from "./poolsApi";
import { choicesToPoolOptions } from "./RolePoolPicker";
import { t } from "../../locale/index";

export interface LocalConnectSectionProps {
  // The project whose roles "Use for agents" pins; Settings with no
  // project selected pins the shared "local" defaults.
  projectId?: string;
  // PLANB X4: how many models the connected runtimes list, so the page
  // below can drop its "no models in this folder" note.
  onRuntimeModels?: (count: number) => void;
}

export function LocalConnectSection(
  props: LocalConnectSectionProps = {},
): ReactElement {
  const roleProject =
    props.projectId !== undefined && props.projectId !== "" ? props.projectId : "local";
  // Locale-current catalog like the Providers page; local rows only.
  const presets = useMemo(
    () => getProviderCatalog().filter((preset) => preset.kind === "local"),
    [],
  );
  const sessionToken = getUiToken() ?? "";
  const [storeInstance] = useState<SecretStorePort>(() =>
    createMemorySecretStore(sessionToken),
  );
  // Served truth: the ids the routes already know (shared with ProvidersPage).
  const [connectedIds, setConnectedIds] = useState<string[]>([]);
  // Probe outcome per preset id: undefined while pending, null when the
  // local server does not answer, a model count otherwise.
  const [probes, setProbes] = useState<Record<string, number | null | undefined>>({});
  // Served real model rows per connected preset (GET
  // /api/v1/providers/{id}/models): read-only names from the runtime,
  // nothing is pulled or deleted from this card.
  const [modelsByPreset, setModelsByPreset] = useState<
    Record<string, ProviderModelRow[]>
  >({});
  const [useModelId, setUseModelId] = useState<Record<string, string>>({});
  const [useMessage, setUseMessage] = useState<Record<string, string>>({});
  const [useSaving, setUseSaving] = useState<Record<string, boolean>>({});
  const [rolesByPreset, setRolesByPreset] = useState<
    Record<string, { role: string; model: string }[]>
  >({});
  const [connectId, setConnectId] = useState<string | null>(null);
  const reportRuntimeModels = props.onRuntimeModels;
  useEffect(() => {
    reportRuntimeModels?.(
      Object.values(modelsByPreset).reduce((sum, rows) => sum + rows.length, 0),
    );
  }, [modelsByPreset, reportRuntimeModels]);
  const [disconnectId, setDisconnectId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listConnectedProviders().then((ids) => {
      if (!cancelled) {
        setConnectedIds(ids);
      }
    });
    void Promise.all(
      presets.map(async (preset) => ({
        id: preset.id,
        count: await probeLocalModels(preset.baseUrl),
      })),
    ).then((outcomes) => {
      if (cancelled) {
        return;
      }
      setProbes((prev) => {
        const next = { ...prev };
        for (const outcome of outcomes) {
          next[outcome.id] = outcome.count;
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [presets]);

  // Served real model names for every connected preset (the local
  // provider model routes answer them; an empty runtime answers empty).
  useEffect(() => {
    let cancelled = false;
    if (connectedIds.length === 0) {
      return undefined;
    }
    void Promise.all(
      connectedIds.map(async (id) => ({
        id,
        rows: (await listProviderModels(id, [])).rows,
      })),
    ).then((entries) => {
      if (cancelled) {
        return;
      }
      setModelsByPreset((prev) => {
        const next = { ...prev };
        for (const entry of entries) {
          next[entry.id] = entry.rows;
        }
        return next;
      });
      setUseModelId((prev) => {
        const next = { ...prev };
        for (const entry of entries) {
          if (next[entry.id] === undefined) {
            const first = entry.rows[0];
            next[entry.id] = first === undefined ? "" : first.id;
          }
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [connectedIds]);

  // R2: pin the chosen real model on the worker through the normal
  // role save, so routing, verification and audit stay the same as
  // for a cloud model. A status line confirms the save.
  async function handleUseForAgents(preset: ProviderPreset): Promise<void> {
    const modelId = useModelId[preset.id] ?? "";
    if (modelId === "" || useSaving[preset.id] === true) {
      return;
    }
    setUseSaving((prev) => ({ ...prev, [preset.id]: true }));
    try {
      const picked = (modelsByPreset[preset.id] ?? []).find(
        (row) => row.id === modelId,
      );
      const options = choicesToPoolOptions([
        {
          providerId: preset.id,
          modelId,
          label: picked?.label ?? modelId,
        },
      ]);
      for (const role of AGENT_ROLES) {
        await saveRolePool(roleProject, role, {
          mode: "PINNED",
          pinnedKey: options[0]?.key ?? "",
          poolKeys: [],
          strategy: "AUTO",
        }, options);
      }
      let rows: RolePoolReadRow[] = [];
      try {
        rows = await readRolePools(roleProject);
      } catch {
        rows = [];
      }
      setRolesByPreset((prev) => ({
        ...prev,
        [preset.id]: AGENT_ROLES.map((role) => {
          const row = rows.find((item) => item.role === role);
          const model = row?.model ?? "";
          return {
            role,
            model: model === "" ? (picked?.label ?? modelId) : model.replace(/^[^/]+\//, ""),
          };
        }),
      }));
      setUseMessage((prev) => ({
        ...prev,
        [preset.id]: t("settings.localAi.workerPinned", {
          model: picked?.label ?? modelId,
        }),
      }));
    } catch (err) {
      const reason =
        err instanceof ApiError && typeof err.details?.message === "string" &&
          err.details.message.trim() !== ""
          ? err.details.message.trim()
          : err instanceof Error && err.message.trim() !== ""
            ? err.message.trim()
            : t("errors.generic");
      setUseMessage((prev) => ({
        ...prev,
        [preset.id]: t("settings.localAi.useFailed", { reason }),
      }));
    } finally {
      setUseSaving((prev) => ({ ...prev, [preset.id]: false }));
    }
  }

  function handleConnected(presetId: string): void {
    // The dialog stays open and moves to step 2 itself (same as the
    // Providers page); only the row state flips underneath it.
    setConnectedIds((prev) =>
      prev.includes(presetId) ? prev : [...prev, presetId],
    );
  }

  function handleDisconnected(secretId: string): void {
    setConnectedIds((prev) =>
      prev.filter((id) => secretIdForProvider(id) !== secretId),
    );
    setDisconnectId(null);
  }

  const connectPreset: ProviderPreset | null =
    connectId === null
      ? null
      : (presets.find((preset) => preset.id === connectId) ?? null);
  const disconnectPreset: ProviderPreset | null =
    disconnectId === null
      ? null
      : (presets.find((preset) => preset.id === disconnectId) ?? null);

  if (presets.length === 0) {
    return (
      <div data-testid="local-connect">
        <p>{t("settings.localAi.empty")}</p>
      </div>
    );
  }

  return (
    <div data-testid="local-connect">
      {presets.map((preset) => {
        const connected = connectedIds.includes(preset.id);
        const probe = probes[preset.id];
        return (
          <article
            key={preset.id}
            data-testid={`local-preset-${preset.id}`}
            data-provider-id={preset.id}
          >
            <h3>{preset.label}</h3>
            <p data-testid={`local-url-${preset.id}`} data-variant="quiet">
              {preset.baseUrl}
            </p>
            {connected ? (
              <>
                {/* R2: status is connected, endpoint, models. */}
                <p role="status" data-variant="quiet">
                  {t("settings.localAi.connectedModels", {
                    label: preset.label,
                    count: String((modelsByPreset[preset.id] ?? []).length),
                  })}
                </p>
                {(modelsByPreset[preset.id] ?? []).length > 0 ? (
                  <label>
                    {t("settings.localAi.modelsLabel")}
                    <select
                      aria-label={t("settings.localAi.modelsLabel")}
                      data-testid={`local-models-${preset.id}`}
                      value={useModelId[preset.id] ?? ""}
                      onChange={(event) =>
                        setUseModelId((prev) => ({
                          ...prev,
                          [preset.id]: event.target.value,
                        }))
                      }
                    >
                      {(modelsByPreset[preset.id] ?? []).map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {(() => {
                  const picked = (modelsByPreset[preset.id] ?? []).find(
                    (row) => row.id === (useModelId[preset.id] ?? ""),
                  );
                  return picked !== undefined && picked.kbKnown === false ? (
                    <p data-variant="quiet" role="note">
                      {t("settings.localAi.noCapability", {
                        model: picked.label,
                      })}
                    </p>
                  ) : null;
                })()}
                <div
                  data-testid={`local-actions-${preset.id}`}
                  style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}
                >
                <button
                  type="button"
                  data-testid={`local-use-${preset.id}`}
                  disabled={
                    (modelsByPreset[preset.id] ?? []).length === 0 ||
                    useSaving[preset.id] === true
                  }
                  onClick={() => {
                    void handleUseForAgents(preset);
                  }}
                >
                  {t("settings.localAi.useForAgents")}
                </button>
                <button
                  type="button"
                  aria-label={t("providers.page.disconnectCta", {
                    label: preset.label,
                  })}
                  onClick={() => setDisconnectId(preset.id)}
                >
                  {t("providers.page.disconnectLabel")}
                </button>
                </div>
                {useMessage[preset.id] !== undefined &&
                useMessage[preset.id] !== "" ? (
                  <p role="status" data-variant="quiet">
                    {useMessage[preset.id]}
                  </p>
                ) : null}
                {rolesByPreset[preset.id] !== undefined ? (
                  <ul data-testid={`local-roles-${preset.id}`}>
                    {rolesByPreset[preset.id].map((item) => (
                      <li key={item.role}>
                        {t(`providers.role.${item.role}`)}: {item.model}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : (
              <>
                <button
                  type="button"
                  aria-label={t("providers.page.connectCta", {
                    label: preset.label,
                  })}
                  onClick={() => setConnectId(preset.id)}
                >
                  {t("providers.page.connectLabel")}
                </button>
                {probe === null ? (
                  <p data-variant="quiet">
                    {t("providers.connect.localNotRunning", {
                      label: preset.label,
                    })}
                  </p>
                ) : null}
              </>
            )}
          </article>
        );
      })}
      <ConnectDialog
        preset_id={connectPreset?.id ?? ""}
        preset={connectPreset}
        open={connectPreset !== null}
        store={storeInstance}
        onClose={() => setConnectId(null)}
        onConnected={handleConnected}
      />
      <DisconnectDialog
        provider_id={disconnectPreset?.id ?? ""}
        providerLabel={disconnectPreset?.label ?? ""}
        secretId={
          disconnectPreset === null
            ? ""
            : secretIdForProvider(disconnectPreset.id)
        }
        open={disconnectPreset !== null}
        store={storeInstance}
        sessionToken={sessionToken}
        onClose={() => setDisconnectId(null)}
        onDisconnected={handleDisconnected}
      />
    </div>
  );
}
