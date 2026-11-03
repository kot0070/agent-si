// FXROLES chat hierarchy rows: Director, Manager and Agents over the chat page.
// Reads and writes the same role profiles the Settings editors use (GET plus
// PUT /api/v1/routing/role with the UI session token, never a second store):
// the Agents row saves worker AND auditor together. The exact model on each
// row is read-only text resolved from the provider catalog, the same catalog
// the Settings editor builds its options from, so there is no model override
// control and no separate auditor provider picker in chat. The collapsed line
// remembers its state per project in localStorage. Profiles load on mount
// even while collapsed, so the collapsed button can name the
// Director/Manager/Agents values at once; before data arrives it carries only
// the Role pools title from the locale files, so the chat page renders no
// hard-coded string before data arrives. Label keys live in the roles
// lane hits record with English
// defaults; missing locale keys fall back to English and no locale file is
// touched here.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { listConnectedProviders } from "../settings/ProvidersPage/connectApi";
import { PROVIDER_CATALOG } from "../settings/ProvidersPage/catalog";
import { AUTO_SENTINEL } from "../settings/ProvidersPage/types";
import type { ProviderPreset } from "../settings/ProvidersPage/types";
import { listProviderModels } from "../settings/ProvidersPage/modelsApi";
import type { ProviderModelRow } from "../settings/ProvidersPage/modelsApi";
import {
  chatCapable,
  choiceLabel,
  isListableModelId,
} from "../settings/ProvidersPage/roleChoices";
import { readRoleProfiles, saveRoleProfile } from "../settings/index";
import type { RoleModelProfile, RoleProfileMap } from "../settings/index";
import { pt } from "./permissions";

type HierarchyRow = "director" | "manager" | "agents";

const CONNECT_HREF = "/settings/models";
const SETTINGS_HREF = "/settings/routing";

function storageKey(projectId: string): string {
  return `agentsi.hierarchy.collapsed.${projectId}`;
}

// FXPANEL: the rows must never sit on a pending load forever (a hung
// route fetch left the expanded section an empty box in the live
// trial). Past this budget the load degrades to the Connect state.
const PROVIDER_LOAD_TIMEOUT_MS = 10000;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const gate = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), ms);
  });
  return Promise.race([promise, gate]).finally(() => {
    if (timer !== null) {
      clearTimeout(timer);
    }
  });
}

function readCollapsed(projectId: string): boolean {
  try {
    return window.localStorage.getItem(storageKey(projectId)) !== "expanded";
  } catch {
    return true;
  }
}

function writeCollapsed(projectId: string, collapsed: boolean): void {
  try {
    window.localStorage.setItem(
      storageKey(projectId),
      collapsed ? "collapsed" : "expanded",
    );
  } catch {
    return;
  }
}

function presetFor(providerId: string): ProviderPreset | undefined {
  return PROVIDER_CATALOG.find((preset) => preset.id === providerId);
}

function autoLabel(): string {
  return pt("chat.hierarchy.auto", "Auto");
}

function exactModelText(profile: RoleModelProfile | undefined): string {
  if (profile === undefined || profile.mode !== "PINNED") {
    return autoLabel();
  }
  const provider = profile.provider;
  const model = profile.model;
  if (provider === undefined || model === undefined) {
    return autoLabel();
  }
  const preset = presetFor(provider);
  const modelLabel = preset?.models.find((entry) => entry.id === model)?.label;
  return `${preset?.label ?? provider} \u2014 ${modelLabel ?? model}`;
}

export type HierarchyModelOption = {
  value: string;
  label: string;
};

/** R8(a): the strip offers real models (provider + model), never
placeholders. Connected providers, then each provider instance's
model list: enabled ticks as full `provider/model` ids. */
export function hierarchyModelOptions(
  connected: string[],
  rowsByProvider: Record<string, ProviderModelRow[]>,
  ticksByProvider: Record<string, string[] | null>,
): HierarchyModelOption[] {
  const seen = new Set<string>();
  const out: HierarchyModelOption[] = [];
  for (const providerId of connected) {
    const preset = presetFor(providerId);
    if (preset === undefined) {
      continue;
    }
    const ticks = ticksByProvider[providerId] ?? null;
    const rows = rowsByProvider[providerId] ?? [];
    const enabled = ticks === null ? rows.map((row) => row.id) : ticks;
    const allowed = new Set<string>();
    for (const id of enabled) {
      allowed.add(id);
      const bare = id.includes("/") ? (id.split("/").pop() ?? id) : id;
      allowed.add(`${providerId}/${bare}`);
      allowed.add(bare);
    }
    for (const row of rows) {
      if (!allowed.has(row.id)) {
        continue;
      }
      if (!isListableModelId(canonicalId(providerId, row.id))) {
        continue;
      }
      if (!chatCapable(row.kb)) {
        continue;
      }
      const full = canonicalId(providerId, row.id);
      if (seen.has(full)) {
        continue;
      }
      seen.add(full);
      out.push({ value: full, label: choiceLabel(preset.label, full) });
    }
  }
  return out;
}

function canonicalId(providerId: string, modelId: string): string {
  const prefix = `${providerId}/`;
  const bare = modelId.startsWith(prefix)
    ? modelId.slice(prefix.length)
    : modelId;
  if (bare === "" || bare.includes("/")) {
    return bare.includes("/") ? modelId : `${providerId}/${bare}`;
  }
  return `${providerId}/${bare}`;
}

function isSplitAuditor(
  worker: RoleModelProfile | undefined,
  auditor: RoleModelProfile | undefined,
): boolean {
  if (auditor === undefined) {
    return false;
  }
  const auditorProvider = auditor.provider;
  if (auditorProvider === undefined || auditorProvider === "") {
    return false;
  }
  const workerProvider = worker === undefined ? undefined : worker.provider;
  return auditorProvider !== workerProvider;
}

export function HierarchyRows({
  projectId,
  onExpandedChange,
}: {
  projectId: string;
  /** FXCHATV (b): the chat composer hides its own Connect CTA while the
      expanded rows already offer one, so one state carries one CTA. */
  onExpandedChange?: (expanded: boolean) => void;
}): ReactElement | null {
  const [connected, setConnected] = useState<string[] | null>(null);
  const [profiles, setProfiles] = useState<RoleProfileMap | null>(null);
  const [modelRows, setModelRows] = useState<Record<string, ProviderModelRow[]>>({});
  const [modelTicks, setModelTicks] = useState<Record<string, string[] | null>>({});
  const [loadFailed, setLoadFailed] = useState(false);
  const [expanded, setExpanded] = useState<boolean>(
    () => !readCollapsed(projectId),
  );

  useEffect(() => {
    setConnected(null);
    setProfiles(null);
    setLoadFailed(false);
    setExpanded(!readCollapsed(projectId));
  }, [projectId]);

  useEffect(() => {
    if (projectId === "") {
      return;
    }
    if (connected !== null && profiles !== null) {
      return;
    }
    let alive = true;
    // FXPANEL: listConnectedProviders swallows its own failures, but the
    // request layer can still reject or hang the Promise.all below
    // (offline, non-2xx, bad JSON, a hung route). A rejection or a past-
    // budget load degrades to the plain Connect state, never to a stuck
    // null that renders an empty box.
    void Promise.all([
      withTimeout(listConnectedProviders(), PROVIDER_LOAD_TIMEOUT_MS),
      withTimeout(
        readRoleProfiles(projectId).catch(
          (): RoleProfileMap => ({}),
        ),
        PROVIDER_LOAD_TIMEOUT_MS,
      ).then((map): RoleProfileMap => map ?? {}),
    ]).then(([ids, map]) => {
      if (!alive) {
        return;
      }
      if (ids === null) {
        setLoadFailed(true);
        setConnected([]);
      } else {
        setConnected(ids);
        // R8(a): real model names per connected provider (served
        // provider model routes); a failing list degrades to no
        // options for that provider, never a placeholder.
        void Promise.all(
          ids.map(async (id) => {
            const preset = presetFor(id);
            try {
              const outcome = await listProviderModels(
                id,
                preset?.models ?? [],
              );
              return { id, rows: outcome.rows, ticks: outcome.servedEnabled };
            } catch {
              return { id, rows: [], ticks: [] as string[] };
            }
          }),
        ).then((entries) => {
          if (!alive) {
            return;
          }
          setModelRows((prev) => {
            const next = { ...prev };
            for (const entry of entries) {
              next[entry.id] = entry.rows;
            }
            return next;
          });
          setModelTicks((prev) => {
            const next = { ...prev };
            for (const entry of entries) {
              next[entry.id] = entry.ticks;
            }
            return next;
          });
        });
      }
      setProfiles(map);
    });
    return () => {
      alive = false;
    };
  }, [projectId, expanded, connected, profiles]);

  function toggle(expandedNext: boolean): void {
    writeCollapsed(projectId, !expandedNext);
    setExpanded(expandedNext);
    onExpandedChange?.(expandedNext);
    if (expandedNext) {
      // FXPANEL: providers may have changed while the rows were hidden
      // (connect/disconnect in Settings): expanding re-reads the list
      // instead of serving the stale one.
      setLoadFailed(false);
      setConnected(null);
      setProfiles(null);
    }
  }

  function retry(): void {
    setLoadFailed(false);
    setConnected(null);
    setProfiles(null);
  }

  function refresh(): void {
    void readRoleProfiles(projectId)
      .then((map) => {
        setProfiles(map);
      })
      .catch(() => undefined);
  }

  async function saveRow(row: HierarchyRow, value: string): Promise<void> {
    if (value === AUTO_SENTINEL) {
      if (row === "agents") {
        await saveRoleProfile(projectId, { role: "worker", mode: "AUTO" });
        await saveRoleProfile(projectId, { role: "auditor", mode: "AUTO" });
      } else {
        await saveRoleProfile(projectId, { role: row, mode: "AUTO" });
      }
      return;
    }
    // R8(a): the strip pins the exact real model (full
    // `provider/model` id), so a bound local model really runs.
    const slash = value.indexOf("/");
    const provider = slash < 0 ? value : value.slice(0, slash);
    const model = value;
    if (row === "agents") {
      await saveRoleProfile(projectId, {
        role: "worker",
        mode: "PINNED",
        provider,
        model,
      });
      await saveRoleProfile(projectId, {
        role: "auditor",
        mode: "PINNED",
        provider,
        model,
      });
      return;
    }
    await saveRoleProfile(projectId, {
      role: row,
      mode: "PINNED",
      provider,
      model,
    });
  }

  function handleChange(row: HierarchyRow, value: string): void {
    void saveRow(row, value)
      .catch(() => undefined)
      .then(() => refresh());
  }

  // FXDESIGN6-D6A: locale-driven role labels (shared by the collapsed
  // summary and the expanded rows, so no hard-coded English role name
  // ever renders as a text node).
  const directorLabel = pt("chat.hierarchy.director", "Director");
  const managerLabel = pt("chat.hierarchy.manager", "Manager");
  const agentsLabel = pt("chat.hierarchy.agents", "Agents");

  if (projectId === "") {
    return (
      <section
        data-testid="hierarchy"
        aria-label={pt("chat.hierarchy.title", "Model hierarchy")}
      >
        <p data-testid="hierarchy-no-project">
          {pt(
            "chat.hierarchy.noProject",
            "Choose a project to set the model hierarchy.",
          )}
        </p>
      </section>
    );
  }

  if (!expanded) {
    return (
      <section
        data-testid="hierarchy"
        aria-label={pt("chat.hierarchy.title", "Model hierarchy")}
      >
        <button
          type="button"
          data-testid="hierarchy-collapsed"
          className="fx-btn-quiet"
          aria-label={pt("chat.hierarchy.expand", "Show model hierarchy")}
          onClick={() => toggle(true)}
        >
          {connected !== null && profiles !== null ? (
            // FXDESIGN6-D6A: one span per locale value; the ": " and
            // middle-dot dividers are CSS (fx-hsummary in shell.css), so
            // the locale-only contract sees exactly the locale values as
            // text nodes. Visual and announced order match the old
            // single-line summary.
            <span className="fx-hsummary">
              <span className="fx-hsummary-item">
                <span>{directorLabel}</span>
                <span>{exactModelText(profiles.director)}</span>
              </span>
              <span className="fx-hsummary-item">
                <span>{managerLabel}</span>
                <span>{exactModelText(profiles.manager)}</span>
              </span>
              <span className="fx-hsummary-item">
                <span>{agentsLabel}</span>
                <span>{exactModelText(profiles.worker)}</span>
              </span>
            </span>
          ) : (
            t("providers.page.rolePoolsTitle")
          )}
        </button>
      </section>
    );
  }

  function renderRow(
    row: HierarchyRow,
    label: string,
    profile: RoleModelProfile | undefined,
    options: HierarchyModelOption[],
    split: boolean,
    /** FXCHATV (b): one Connect CTA per state — only the first empty
        row carries the link, the rest name the empty state quietly. */
    showConnect: boolean,
  ): ReactElement {
    // R8(a): the select offers real models; the chosen one shows once
    // (no separate model text beside the select).
    const pinnedFull =
      profile !== undefined &&
      profile.mode === "PINNED" &&
      profile.provider !== undefined &&
      profile.model !== undefined
        ? `${profile.provider}/${profile.model.startsWith(`${profile.provider}/`) ? profile.model.slice(profile.provider.length + 1) : profile.model}`
        : null;
    const selected =
      pinnedFull !== null && options.some((option) => option.value === pinnedFull)
        ? pinnedFull
        : AUTO_SENTINEL;
    return (
      <div data-testid={`hierarchy-row-${row}`}>
        <span data-testid={`hierarchy-label-${row}`}>{label}</span>{" "}
        {options.length === 0 ? (
          showConnect ? (
            <a data-testid="hierarchy-connect-link" href={CONNECT_HREF}>
              {pt("chat.hierarchy.connect", "Connect a provider")}
            </a>
          ) : null
        ) : (
          <select
            data-testid={`hierarchy-select-${row}`}
            aria-label={label}
            value={selected}
            onChange={(event) => handleChange(row, event.target.value)}
          >
            <option value={AUTO_SENTINEL}>{autoLabel()}</option>
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}
        {row === "agents" && split ? (
          <p data-testid="hierarchy-auditor-split">
            {pt(
              "chat.hierarchy.auditorSplit",
              "The auditor uses a different provider.",
            )}
          </p>
        ) : null}
        {row === "agents" && split ? (
          <a data-testid="hierarchy-settings-link" href={SETTINGS_HREF}>
            {pt("chat.hierarchy.openSettings", "Open Settings")}
          </a>
        ) : null}
      </div>
    );
  }

  const emptyProviders = connected !== null && connected.length === 0;
  const loadingRows = connected === null || profiles === null;
  // FXPANEL: rejection degrades to the empty list (see the loader
  // above), so failure and genuinely-empty providers share one plain
  // Connect state with its action; the rows below keep their contract
  // (the Director row carries the link, no selects render).
  const connectText = pt("chat.hierarchy.connect", "Connect a provider");
  const options =
    connected === null
      ? []
      : hierarchyModelOptions(connected, modelRows, modelTicks);
  const rows =
    connected !== null && profiles !== null && connected.length > 0 ? (
      <>
        {renderRow(
          "director",
          directorLabel,
          profiles.director,
          options,
          false,
          false,
        )}
        {renderRow("manager", managerLabel, profiles.manager, options, false, false)}
        {renderRow(
          "agents",
          agentsLabel,
          profiles.worker,
          options,
          isSplitAuditor(profiles.worker, profiles.auditor),
          false,
        )}
      </>
    ) : connected !== null && profiles !== null ? (
      <>
        {renderRow(
          "director",
          directorLabel,
          profiles.director,
          options,
          false,
          emptyProviders,
        )}
        {renderRow("manager", managerLabel, profiles.manager, options, false, false)}
        {renderRow(
          "agents",
          agentsLabel,
          profiles.worker,
          options,
          isSplitAuditor(profiles.worker, profiles.auditor),
          false,
        )}
      </>
    ) : null;
  return (
    <section
      data-testid="hierarchy"
      aria-label={pt("chat.hierarchy.title", "Model hierarchy")}
    >
      <h2>{pt("chat.hierarchy.title", "Model hierarchy")}</h2>
      <button
        type="button"
        data-testid="hierarchy-collapse"
        className="fx-btn-quiet"
        aria-label={pt("chat.hierarchy.collapse", "Hide model hierarchy")}
        onClick={() => toggle(false)}
      >
        {pt("chat.hierarchy.collapse", "Hide model hierarchy")}
      </button>
      {loadingRows ? (
        <p data-testid="hierarchy-loading">
          {pt("watcher.tab.loading", "Loading...")}
        </p>
      ) : null}
      {emptyProviders ? (
        <>
          <p data-testid="hierarchy-empty">{connectText}</p>
          {loadFailed ? (
            <button
              type="button"
              data-testid="hierarchy-retry"
              className="fx-btn-quiet"
              onClick={retry}
            >
              {pt("chat.error.retry", "Retry")}
            </button>
          ) : null}
        </>
      ) : null}
      {rows}
    </section>
  );
}
