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
import { readRoleProfiles, saveRoleProfile } from "../settings/index";
import type { RoleModelProfile, RoleProfileMap } from "../settings/index";
import { pt } from "./permissions";

type HierarchyRow = "director" | "manager" | "agents";

const CONNECT_HREF = "/settings/models";
const SETTINGS_HREF = "/settings/routing";

function storageKey(projectId: string): string {
  return `agentsi.hierarchy.collapsed.${projectId}`;
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

function providerLabel(providerId: string): string {
  return presetFor(providerId)?.label ?? providerId;
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

function resolveModel(
  providerId: string,
  current: RoleModelProfile | undefined,
): string {
  if (
    current !== undefined &&
    current.mode === "PINNED" &&
    current.provider === providerId &&
    current.model !== undefined
  ) {
    return current.model;
  }
  const first = presetFor(providerId)?.models[0];
  if (first !== undefined) {
    return first.id;
  }
  return providerId;
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
  const [expanded, setExpanded] = useState<boolean>(
    () => !readCollapsed(projectId),
  );

  useEffect(() => {
    setConnected(null);
    setProfiles(null);
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
    void Promise.all([
      listConnectedProviders(),
      readRoleProfiles(projectId).catch(
        (): RoleProfileMap => ({}),
      ),
    ]).then(([ids, map]) => {
      if (!alive) {
        return;
      }
      setConnected(ids);
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
    if (row === "agents") {
      const agentsModel = resolveModel(
        value,
        profiles === null ? undefined : profiles.worker,
      );
      await saveRoleProfile(projectId, {
        role: "worker",
        mode: "PINNED",
        provider: value,
        model: agentsModel,
      });
      await saveRoleProfile(projectId, {
        role: "auditor",
        mode: "PINNED",
        provider: value,
        model: agentsModel,
      });
      return;
    }
    const current =
      profiles === null
        ? undefined
        : row === "director"
          ? profiles.director
          : profiles.manager;
    await saveRoleProfile(projectId, {
      role: row,
      mode: "PINNED",
      provider: value,
      model: resolveModel(value, current),
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
    ids: string[],
    split: boolean,
    /** FXCHATV (b): one Connect CTA per state — only the first empty
        row carries the link, the rest name the empty state quietly. */
    showConnect: boolean,
  ): ReactElement {
    const selected =
      profile !== undefined &&
      profile.mode === "PINNED" &&
      profile.provider !== undefined
        ? profile.provider
        : AUTO_SENTINEL;
    const options =
      selected === AUTO_SENTINEL || ids.includes(selected)
        ? ids
        : [...ids, selected];
    return (
      <div data-testid={`hierarchy-row-${row}`}>
        <span data-testid={`hierarchy-label-${row}`}>{label}</span>
        <span data-testid={`hierarchy-model-${row}`}>
          {exactModelText(profile)}
        </span>
        {ids.length === 0 ? (
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
            {options.map((providerId) => (
              <option key={providerId} value={providerId}>
                {providerLabel(providerId)}
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

  const emptyRows = connected !== null && connected.length === 0;
  const rows =
    connected !== null && profiles !== null ? (
      <>
        {renderRow(
          "director",
          directorLabel,
          profiles.director,
          connected,
          false,
          emptyRows,
        )}
        {renderRow("manager", managerLabel, profiles.manager, connected, false, false)}
        {renderRow(
          "agents",
          agentsLabel,
          profiles.worker,
          connected,
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
      {rows}
    </section>
  );
}
