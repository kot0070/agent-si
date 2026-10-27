/** K03 STEP2: runner view (rows 246, M-P4-155).
 *
 * Counters, per-test rows and output opening over one run snapshot. The
 * snapshot is read once via fetch at import time (top-level await), so the
 * exported helpers stay synchronous. All view data enters only through the
 * fetch boundary; no hand-built run object is passed as an argument.
 */

const runResponse = await globalThis.fetch("/api/stage/run");
const runPayload = await runResponse.json();
const cachedResults = Array.isArray(runPayload.results)
  ? runPayload.results
  : [];

const ACTIVE_STATUSES = new Set(["RUNNING", "ACTIVE", "IN_PROGRESS"]);

/** {active, passed, remaining} with remaining = total - passed. */
export function runnerCounters() {
  let passed = 0;
  let active = 0;
  for (const result of cachedResults) {
    if (result.status === "PASS") {
      passed += 1;
    }
    if (ACTIVE_STATUSES.has(result.status)) {
      active += 1;
    }
  }
  return { active, passed, remaining: cachedResults.length - passed };
}

/** One row per result in payload order, each with test_id and status. */
export function runnerTestRows() {
  return cachedResults.map((result) => ({
    test_id: result.test_id,
    status: result.status,
    output_ref: result.output_ref,
  }));
}

/** {test_id, content_ref} of the row whose output_ref matches ref. */
export function openTestOutput(ref) {
  const row = cachedResults.find((result) => result.output_ref === ref);
  return { test_id: row.test_id, content_ref: row.output_ref };
}
