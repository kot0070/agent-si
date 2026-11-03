// Per-role PINNED / pool / AUTO editing for one project role.
// Option keys are opaque: only labels are shown, never raw pool or model ids.
// A key resolves to (provider, model) through the default in-memory map
// built from the internally resolved enabled choices.

import { useEffect, useMemo, useRef, useState } from "react";
import { getProviderCatalog } from "./catalog";
import { enabledChatChoices } from "./ChatSelector";
import type { ChatChoice } from "./ChatSelector";
import { readRolePoolState } from "../roleProfilesApi";
import type { RolePoolSaved } from "../roleProfilesApi";
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

// Map one saved server state onto opaque option keys. A saved
// provider/model the options no longer list becomes a synthetic
// `missing:` key with an extra option so it still shows (marked
// unavailable by the caller) instead of silently falling back to AUTO.
export function mapSavedToValue(
  saved: RolePoolSaved,
  options: PoolOption[],
): { value: RolePoolValue; extra: PoolOption[] } {
  const byMember = new Map<string, string>();
  for (const option of options) {
    const key = `${option.providerId}\0${option.modelId}`;
    if (!byMember.has(key)) {
      byMember.set(key, option.key);
    }
  }
  const extra: PoolOption[] = [];
  function keyFor(provider: string, model: string): string {
    const known = byMember.get(`${provider}\0${model}`);
    if (known !== undefined) {
      return known;
    }
    const synthetic = `missing:${provider}/${model}`;
    if (!extra.some((option) => option.key === synthetic)) {
      extra.push({
        key: synthetic,
        label: `${provider} — ${model}`,
        providerId: provider,
        modelId: model,
      });
    }
    return synthetic;
  }
  const strategy =
    saved.strategy === "DIRECTOR_PER_TASK" ||
    saved.strategy === "AUTO" ||
    saved.strategy === "FALLBACK_ORDER" ||
    saved.strategy === "SPLIT_PARALLEL"
      ? saved.strategy
      : "AUTO";
  if (saved.mode === "PINNED") {
    const provider = saved.provider ?? "";
    const model = saved.model ?? "";
    if (provider === "" || model === "") {
      return {
        value: { mode: "PINNED", pinnedKey: "", poolKeys: [], strategy },
        extra,
      };
    }
    return {
      value: {
        mode: "PINNED",
        pinnedKey: keyFor(provider, model),
        poolKeys: [],
        strategy,
      },
      extra,
    };
  }
  if (saved.mode === "pool") {
    return {
      value: {
        mode: "pool",
        pinnedKey: "",
        poolKeys: saved.pool.map((member) =>
          keyFor(member.provider, member.model),
        ),
        strategy,
      },
      extra,
    };
  }
  return {
    value: { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy },
    extra,
  };
}

type RolePoolPickerProps = {
  role: string;
  project_id: string;
  options?: PoolOption[];
  onChange?: (value: RolePoolValue) => void;
};

const DEFAULT_VALUE: RolePoolValue = { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy: "AUTO" };

export function RolePoolPicker({ role, project_id = "local", options, onChange }: RolePoolPickerProps) {
  const project = project_id;
  const baseOptions = useMemo<PoolOption[]>(
    () => options ?? choicesToPoolOptions(enabledChatChoices(getProviderCatalog(), {})),
    [options],
  );
  // Keys the server saved but the current options no longer list (a
  // provider/model removed after the save). They still render, marked
  // unavailable, and the role never silently falls back to AUTO.
  const [extraOptions, setExtraOptions] = useState<PoolOption[]>([]);
  const poolOptions = useMemo<PoolOption[]>(
    () => [...baseOptions, ...extraOptions],
    [baseOptions, extraOptions],
  );
  const resolve = defaultPoolResolver(poolOptions);
  const [current, setInner] = useState<RolePoolValue>(DEFAULT_VALUE);
  // Raw saved state (one GET per mount). Mapping to option keys re-runs
  // when the options arrive late (served listings load after mount) but
  // never after the user touches the picker (emit marks touched).
  const [saved, setSaved] = useState<RolePoolSaved | null>(null);
  const touchedRef = useRef(false);
  useEffect(() => {
    let cancelled = false;
    void readRolePoolState(project, role).then((state) => {
      if (!cancelled && state !== undefined) {
        setSaved(state);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [project, role]);
  useEffect(() => {
    // FXSAVED item 2: show the saved PINNED/pool/AUTO after restart.
    // setInner only: a load never calls onChange and never writes.
    if (touchedRef.current || saved === null) {
      return;
    }
    const mapped = mapSavedToValue(saved, baseOptions);
    setExtraOptions(mapped.extra);
    setInner(mapped.value);
  }, [saved, baseOptions]);
  const label = roleLabel(role);
  const group = `role-pool-${project}-${role}-mode`;
  // Synthetic keys for saved-but-unlisted members, for the unavailable mark.
  const missingKeys = useMemo(
    () => new Set(extraOptions.map((option) => option.key)),
    [extraOptions],
  );

  function emit(next: RolePoolValue): void {
    touchedRef.current = true;
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
    <fieldset data-testid="role-pool-picker" data-role={role} data-project-id={project} className="fx-card">
      <legend>{label}</legend>
      {/* R6: radio directly before its label, one compact row. */}
      <div className="fx-modes-row">
        {MODES.map((mode) => (
          <label key={mode} className="fx-radio-row">
            <input
              type="radio"
              name={group}
              checked={current.mode === mode}
              onChange={() => emit({ ...current, mode })}
            />
            {modeLabel(mode)}
          </label>
        ))}
      </div>
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
                {missingKeys.has(option.key)
                  ? `${option.label} (unavailable)`
                  : option.label}
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
                <label className="fx-radio-row">
                  <input
                    type="checkbox"
                    checked={current.poolKeys.includes(option.key)}
                    onChange={() => togglePoolKey(option.key)}
                  />
                  {missingKeys.has(option.key)
                    ? `${option.label} (unavailable)`
                    : option.label}
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
