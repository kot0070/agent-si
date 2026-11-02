// Per-role PINNED / pool / AUTO editing for one project role.
// Option keys are opaque: only labels are shown, never raw pool or model ids.
// A key resolves to (provider, model) through the default in-memory map
// built from the internally resolved enabled choices.

import { useEffect, useRef, useState } from "react";
import { PROVIDER_CATALOG } from "./catalog";
import { enabledChatChoices } from "./ChatSelector";
import type { ChatChoice } from "./ChatSelector";
import { roleLabel } from "./types";
import { t } from "../../locale/index";

export type RolePoolMode = "PINNED" | "pool" | "AUTO";

export type PoolStrategy = "DIRECTOR_PER_TASK" | "AUTO" | "FALLBACK_ORDER" | "SPLIT_PARALLEL";

export const POOL_STRATEGY_LABELS: Record<PoolStrategy, string> = {
  DIRECTOR_PER_TASK: "Director picks per task",
  AUTO: "Automatic routing",
  FALLBACK_ORDER: "Try in order, fall back on failure",
  SPLIT_PARALLEL: "Draft locally, verify in the cloud",
};

function strategyLabel(strategy: PoolStrategy): string {
  if (strategy === "DIRECTOR_PER_TASK") {
    return t("providers.rolepool.strategyDirectorPerTask");
  }
  if (strategy === "FALLBACK_ORDER") {
    return t("providers.rolepool.strategyFallbackOrder");
  }
  if (strategy === "SPLIT_PARALLEL") {
    return t("providers.rolepool.strategySplitParallel");
  }
  return t("providers.rolepool.strategyAuto");
}

function strategyHelp(strategy: PoolStrategy): string {
  if (strategy === "DIRECTOR_PER_TASK") {
    return t("providers.rolepool.strategyHelpDirectorPerTask");
  }
  if (strategy === "FALLBACK_ORDER") {
    return t("providers.rolepool.strategyHelpFallbackOrder");
  }
  if (strategy === "SPLIT_PARALLEL") {
    return t("providers.rolepool.strategyHelpSplitParallel");
  }
  return t("providers.rolepool.strategyHelpAuto");
}

function modeLabel(mode: RolePoolMode): string {
  if (mode === "PINNED") {
    return t("providers.rolepool.modePinned");
  }
  if (mode === "pool") {
    return t("providers.rolepool.modePool");
  }
  return t("providers.rolepool.modeAuto");
}

function modeHelp(mode: RolePoolMode): string {
  if (mode === "PINNED") {
    return t("providers.rolepool.helpPinned");
  }
  if (mode === "pool") {
    return t("providers.rolepool.helpPool");
  }
  return t("providers.rolepool.helpAuto");
}

const MODES: RolePoolMode[] = ["PINNED", "pool", "AUTO"];

const STRATEGIES: PoolStrategy[] = ["DIRECTOR_PER_TASK", "AUTO", "FALLBACK_ORDER", "SPLIT_PARALLEL"];

export type PoolOption = {
  key: string;
  label: string;
  providerId: string;
  modelId: string;
};

export type RolePoolValue = {
  mode: RolePoolMode;
  pinnedKey: string;
  poolKeys: string[];
  strategy: PoolStrategy;
};

export type ResolvedChoice = {
  provider: string;
  model: string;
};

export function defaultPoolResolver(options: PoolOption[]): (key: string) => ResolvedChoice | undefined {
  const map = new Map<string, ResolvedChoice>();
  for (const option of options) {
    if (!map.has(option.key)) {
      map.set(option.key, { provider: option.providerId, model: option.modelId });
    }
  }
  return (key: string) => map.get(key);
}

export function choicesToPoolOptions(choices: ChatChoice[]): PoolOption[] {
  return choices.map((choice, index) => ({
    key: `pool-opt-${index + 1}`,
    label: choice.label,
    providerId: choice.providerId,
    modelId: choice.modelId,
  }));
}

type RolePoolPickerProps = {
  role: string;
  project_id: string;
  options?: PoolOption[];
  onChange?: (value: RolePoolValue) => void;
};

const DEFAULT_VALUE: RolePoolValue = { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy: "AUTO" };

type SavedPoolProfile = {
  mode?: unknown;
  provider?: unknown;
  model?: unknown;
  pool?: Array<{ provider_id?: unknown; model?: unknown }>;
  strategy?: unknown;
};

function savedStrategy(value: unknown): PoolStrategy {
  return value === "DIRECTOR_PER_TASK" ||
    value === "FALLBACK_ORDER" ||
    value === "SPLIT_PARALLEL" ||
    value === "AUTO"
    ? value
    : "AUTO";
}

// FXUIB-B3: the served profile back onto option keys (labels stay
// label-only). Null when the saved pick no longer resolves (unknown
// mode, unknown models): the caller keeps the default then.
export function savedPoolToValue(
  saved: SavedPoolProfile,
  options: PoolOption[],
): RolePoolValue | null {
  if (saved.mode !== "PINNED" && saved.mode !== "pool" && saved.mode !== "AUTO") {
    return null;
  }
  const strategy = savedStrategy(saved.strategy);
  if (saved.mode === "AUTO") {
    return { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy };
  }
  if (saved.mode === "PINNED") {
    const hit = options.find(
      (option) =>
        option.providerId === saved.provider && option.modelId === saved.model,
    );
    return hit === undefined
      ? null
      : { mode: "PINNED", pinnedKey: hit.key, poolKeys: [], strategy };
  }
  const keys: string[] = [];
  for (const member of saved.pool ?? []) {
    const hit = options.find(
      (option) =>
        option.providerId === member?.provider_id &&
        option.modelId === member?.model,
    );
    if (hit !== undefined && !keys.includes(hit.key)) {
      keys.push(hit.key);
    }
  }
  return keys.length === 0
    ? null
    : { mode: "pool", pinnedKey: "", poolKeys: keys, strategy };
}

export function RolePoolPicker({ role, project_id = "local", options, onChange }: RolePoolPickerProps) {
  const project = project_id;
  const poolOptions = options ?? choicesToPoolOptions(enabledChatChoices(PROVIDER_CATALOG, {}));
  const resolve = defaultPoolResolver(poolOptions);
  const [current, setInner] = useState<RolePoolValue>(DEFAULT_VALUE);
  // FXUIB-B3: the saved profile shows after mount (read-only GET at the
  // network boundary only, applied once per project+role; user edits
  // after that are never clobbered by late option loads).
  const appliedRef = useRef<string | null>(null);
  useEffect(() => {
    const scope = `${project_id}\n${role}`;
    if (appliedRef.current === scope) {
      return;
    }
    let alive = true;
    void (async () => {
      try {
        const response = await fetch(
          `/api/v1/roles/pools/profile?project_id=${encodeURIComponent(project_id)}&role=${encodeURIComponent(role)}`,
        );
        if (!alive || !response.ok) {
          return;
        }
        const next = savedPoolToValue(
          (await response.json()) as SavedPoolProfile,
          poolOptions,
        );
        if (alive && next !== null) {
          appliedRef.current = scope;
          setInner(next);
        }
      } catch {
        return;
      }
    })();
    return () => {
      alive = false;
    };
  }, [project_id, role, poolOptions]);
  const label = roleLabel(role);
  const group = `role-pool-${project}-${role}-mode`;

  function emit(next: RolePoolValue): void {
    setInner(next);
    // FXUIB-B6: an empty pool never saves (the PUT would 400 with no
    // binding stored): the hint below covers it until at least one
    // model is picked. Leaving pool mode always saves.
    if (next.mode === "pool" && next.poolKeys.length === 0) {
      return;
    }
    onChange?.(next);
  }

  function known(key: string): boolean {
    return resolve(key) !== undefined;
  }

  function togglePoolKey(key: string): void {
    if (!known(key)) {
      return;
    }
    const has = current.poolKeys.includes(key);
    emit({
      ...current,
      poolKeys: has ? current.poolKeys.filter((member) => member !== key) : [...current.poolKeys, key],
    });
  }

  return (
    <fieldset data-testid="role-pool-picker" data-role={role} data-project-id={project}>
      <legend>{label}</legend>
      {MODES.map((mode) => (
        <label key={mode}>
          <input
            type="radio"
            name={group}
            checked={current.mode === mode}
            onChange={() => emit({ ...current, mode })}
          />
          {modeLabel(mode)}
        </label>
      ))}
      <p>{modeHelp(current.mode)}</p>
      {current.mode === "pool" && current.poolKeys.length === 0 ? (
        <p data-testid="pool-empty-hint" role="note">
          {t("providers.rolepool.emptyPoolHint")}
        </p>
      ) : null}
      {current.mode === "PINNED" ? (
        <label>
          {t("providers.rolepool.pinnedAria", { role: label })}
          <select
            aria-label={t("providers.rolepool.pinnedAria", { role: label })}
            value={current.pinnedKey}
            onChange={(event) => {
              if (event.target.value === "" || known(event.target.value)) {
                emit({ ...current, pinnedKey: event.target.value });
              }
            }}
          >
            <option value="">{t("providers.rolepool.selectOption")}</option>
            {poolOptions.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {current.mode === "pool" ? (
        <div>
          <ul>
            {poolOptions.map((option) => (
              <li key={option.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={current.poolKeys.includes(option.key)}
                    onChange={() => togglePoolKey(option.key)}
                  />
                  {option.label}
                </label>
              </li>
            ))}
          </ul>
          <label>
            {t("providers.rolepool.strategyAria", { role: label })}
            <select
              aria-label={t("providers.rolepool.strategyAria", { role: label })}
              value={current.strategy}
              onChange={(event) => emit({ ...current, strategy: event.target.value as PoolStrategy })}
            >
              {STRATEGIES.map((strategy) => (
                <option key={strategy} value={strategy}>
                  {strategyLabel(strategy)}
                </option>
              ))}
            </select>
          </label>
          <p>{strategyHelp(current.strategy)}</p>
        </div>
      ) : null}
    </fieldset>
  );
}
