// Local presets connect block for Settings -> Local LLM (the localAI route).
// One row per kind-local preset (Ollama, LM Studio): label, base URL, served
// connected state, and the SAME ConnectDialog / DisconnectDialog the Providers
// page uses, so both pages share one served truth (listConnectedProviders) and
// one dialog flow. The stored bench panel stays below this block in App.tsx.
// A preset whose probe finds no server shows the existing localNotRunning
// sentence; an empty catalog shows one sentence telling what to do.

import { useEffect, useMemo, useState } from "react";
import type { ReactElement } from "react";
import { getUiToken } from "../../api/errors";
import { listConnectedProviders, probeLocalModels } from "./connectApi";
import { getProviderCatalog } from "./catalog";
import { ConnectDialog } from "./ConnectDialog";
import { DisconnectDialog } from "./DisconnectDialog";
import { createMemorySecretStore, secretIdForProvider } from "./secretStore";
import type { SecretStorePort } from "./secretStore";
import type { ProviderPreset } from "./types";
import { t } from "../../locale/index";

export function LocalConnectSection(): ReactElement {
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
  const [connectId, setConnectId] = useState<string | null>(null);
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
                <p role="status" data-variant="quiet">
                  {t("providers.connect.connected", { label: preset.label })}
                </p>
                <button
                  type="button"
                  aria-label={t("providers.page.disconnectCta", {
                    label: preset.label,
                  })}
                  onClick={() => setDisconnectId(preset.id)}
                >
                  {t("providers.page.disconnectLabel")}
                </button>
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
