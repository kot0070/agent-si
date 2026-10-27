/** K03 STEP2: TEST stage view (rows R-347, M-P4-155).
 *
 * Project settings switch for local tests plus the informational Tests tab
 * descriptor. All view data enters only through the fetch boundary; this
 * module never takes a hand-built settings object as an argument.
 */

let localTestsOverride = undefined;

async function readSettingsPayload() {
  const response = await globalThis.fetch("/api/project/settings");
  return response.json();
}

/** Current local-tests switch value: in-memory override wins, else fetch. */
export async function localTestsEnabled() {
  if (localTestsOverride !== undefined) {
    return localTestsOverride;
  }
  const payload = await readSettingsPayload();
  return Boolean(payload.local_tests);
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
