// Per-role PINNED / pool / AUTO editing for one project role.
// Option keys are opaque: only labels are shown, never raw pool or model ids.
// A key resolves to (provider, model) through the default in-memory map
// built from the internally resolved enabled choices.

import { useState } from "react";
import { PROVIDER_CATALOG } from "./catalog";
import { enabledChatChoices } from "./ChatSelector";
import type { ChatChoice } from "./ChatSelector";
import { ROLE_LABELS } from "./types";

export type RolePoolMode = "PINNED" | "pool" | "AUTO";

export type PoolStrategy = "DIRECTOR_PER_TASK" | "AUTO" | "FALLBACK_ORDER" | "SPLIT_PARALLEL";

export const POOL_STRATEGY_LABELS: Record<PoolStrategy, string> = {
  DIRECTOR_PER_TASK: "Director picks per task",
  AUTO: "Automatic routing",
  FALLBACK_ORDER: "Try in order, fall back on failure",
  SPLIT_PARALLEL: "Draft locally, verify in the cloud",
};

const STRATEGY_HELP: Record<PoolStrategy, string> = {
  DIRECTOR_PER_TASK: "The Director chooses a pool member per task.",
  AUTO: "Pool members are chosen automatically on task fit, price and quality.",
  FALLBACK_ORDER: "Pool members are tried in listed order; on failure the next member takes over.",
  SPLIT_PARALLEL: "A local draft is verified in the cloud.",
};

const MODE_LABELS: Record<RolePoolMode, string> = {
  PINNED: "Pinned model",
  pool: "Model pool",
  AUTO: "Automatic",
};

const MODE_HELP: Record<RolePoolMode, string> = {
  PINNED: "Always use this one model for the role.",
  pool: "Choose from these models by strategy.",
  AUTO: "Route on task fit, price and quality. No fixed model.",
};

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

export function RolePoolPicker({ role, project_id = "local", options, onChange }: RolePoolPickerProps) {
  const project = project_id;
  const poolOptions = options ?? choicesToPoolOptions(enabledChatChoices(PROVIDER_CATALOG, {}));
  const resolve = defaultPoolResolver(poolOptions);
  const [current, setInner] = useState<RolePoolValue>(DEFAULT_VALUE);
  const roleLabel = (ROLE_LABELS as Record<string, string>)[role] ?? role;
  const group = `role-pool-${project}-${role}-mode`;

  function emit(next: RolePoolValue): void {
    setInner(next);
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
      <legend>{roleLabel}</legend>
      {MODES.map((mode) => (
        <label key={mode}>
          <input
            type="radio"
            name={group}
            checked={current.mode === mode}
            onChange={() => emit({ ...current, mode })}
          />
          {MODE_LABELS[mode]}
        </label>
      ))}
      <p>{MODE_HELP[current.mode]}</p>
      {current.mode === "PINNED" ? (
        <label>
          {`${roleLabel} pinned model`}
          <select
            aria-label={`${roleLabel} pinned model`}
            value={current.pinnedKey}
            onChange={(event) => {
              if (event.target.value === "" || known(event.target.value)) {
                emit({ ...current, pinnedKey: event.target.value });
              }
            }}
          >
            <option value="">Select a model</option>
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
            {`${roleLabel} pool strategy`}
            <select
              aria-label={`${roleLabel} pool strategy`}
              value={current.strategy}
              onChange={(event) => emit({ ...current, strategy: event.target.value as PoolStrategy })}
            >
              {STRATEGIES.map((strategy) => (
                <option key={strategy} value={strategy}>
                  {POOL_STRATEGY_LABELS[strategy]}
                </option>
              ))}
            </select>
          </label>
          <p>{STRATEGY_HELP[current.strategy]}</p>
        </div>
      ) : null}
    </fieldset>
  );
}
