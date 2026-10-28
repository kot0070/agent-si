// Setup wizard: per-role pick-or-AUTO. Every role starts on Automatic;
// there is no built-in vendor or model default. Options come from props.
//
// RolePoolPicker reuse: each row below mirrors RolePoolPicker semantics
// (opaque choice keys shown by label, AUTO default, per-role pick-or-AUTO).
// Full PINNED / pool / AUTO editing with plain-language strategies lives in
// RolePoolPicker, embedded beside this wizard on the Providers page; this
// wizard stays pick-or-AUTO so a fresh install finishes with explicit picks.

import { useState } from "react";
import { AUTO_SENTINEL, ROLE_KEYS, ROLE_LABELS } from "./types";
import type { ChatChoice } from "./ChatSelector";
import type { RoleAssignment, RoleKey } from "./types";

type SetupWizardProps = {
  choices: ChatChoice[];
  initial?: RoleAssignment;
  onDone: (assignment: RoleAssignment) => void;
};

function autoAssignment(): RoleAssignment {
  return {
    director: AUTO_SENTINEL,
    manager: AUTO_SENTINEL,
    worker: AUTO_SENTINEL,
    auditor: AUTO_SENTINEL,
    watcher: AUTO_SENTINEL,
  };
}

export function SetupWizard({ choices, initial, onDone }: SetupWizardProps) {
  const [assignment, setAssignment] = useState<RoleAssignment>(() => ({
    ...autoAssignment(),
    ...initial,
  }));

  function pick(role: RoleKey, value: string): void {
    setAssignment((prev) => ({ ...prev, [role]: value }));
  }

  return (
    <div>
      <h1>Setup wizard</h1>
      <p>Choose a model per role, or leave a role on Automatic.</p>
      {ROLE_KEYS.map((role) => (
        <label key={role}>
          {ROLE_LABELS[role]}
          <select
            aria-label={ROLE_LABELS[role]}
            value={assignment[role]}
            onChange={(event) => pick(role, event.target.value)}
          >
            <option value={AUTO_SENTINEL}>Automatic</option>
            {choices.map((choice) => (
              <option key={`${choice.providerId}/${choice.modelId}`} value={choice.modelId}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
      ))}
      <button
        type="button"
        onClick={() => {
          onDone(assignment);
        }}
      >
        Finish setup
      </button>
    </div>
  );
}
