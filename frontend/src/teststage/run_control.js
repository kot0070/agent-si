/** DEMOF13F1 F1: catalog run control.
 *
 * The run control calls POST /api/v1/catalog/run with a suite name
 * and shows the ran count from the reply (ok boolean plus ran
 * integer). State stays in the control: run() records the latest
 * count and ranText() renders it.
 */
export const CATALOG_RUN_ROUTE = "/api/v1/catalog/run";

/**
 * Run one catalog suite.
 * @param {string} suite
 * @returns {Promise<{ ok: boolean, ran: number }>}
 */
export async function runSuite(suite) {
  const res = await fetch(CATALOG_RUN_ROUTE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ suite }),
  });
  if (!res.ok) {
    throw new Error("catalog run failed: " + res.status);
  }
  const data = await res.json();
  return {
    ok: data.ok === true,
    ran: typeof data.ran === "number" ? data.ran : 0,
  };
}

/**
 * @returns {{ ranCount: () => number, ranText: () => string, lastOk: () => boolean, run: (suite: string) => Promise<{ ok: boolean, ran: number }> }}
 * a run control holding the latest ran count.
 */
export function createRunControl() {
  let ranCount = 0;
  let lastOk = false;
  return {
    ranCount: () => ranCount,
    ranText: () => "ran " + ranCount,
    lastOk: () => lastOk,
    run: async (suite) => {
      const outcome = await runSuite(suite);
      lastOk = outcome.ok;
      if (outcome.ok) {
        ranCount = outcome.ran;
      }
      return outcome;
    },
  };
}
