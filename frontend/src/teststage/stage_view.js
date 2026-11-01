/** K03 STEP2: TEST stage view (rows R-347, M-P4-155).
 *
 * Project settings switch for local tests plus the informational Tests tab
 * descriptor. All view data enters only through the fetch boundary; this
 * module never takes a hand-built settings object as an argument.
 */

let localTestsOverride = undefined;

async function readSettingsPayload() {
  // FXWIRE1: the local-tests switch over the real settings defaults
// (src/agent_si/backend/test_runners/k03wire.py settings defaults;
// project_id defaults to global on the wire).
const response = await globalThis.fetch("/api/v1/teststage/settings/defaults");
  return response.json();
}

/** Current local-tests switch value: in-memory override wins, else fetch.
 * Global default is ON: a missing payload or a missing flag reads True. */
export async function localTestsEnabled() {
  if (localTestsOverride !== undefined) {
    return localTestsOverride;
  }
  const payload = await readSettingsPayload();
  if (payload === null || payload === undefined) {
    return true;
  }
  const flag = payload.local_tests ?? payload.enabled;
  if (flag === undefined) {
    return true;
  }
  return Boolean(flag);
}

/** Persist the switch choice as an in-memory override; returns Boolean(v). */
export async function setLocalTestsEnabled(value) {
  localTestsOverride = Boolean(value);
  return localTestsOverride;
}

/** The Tests tab is informational: it carries no settings controls. */
export function testsTabDescriptor() {
  return {
    id: "tests",
    title: "Tests",
    settings_controls: [],
  };
}
