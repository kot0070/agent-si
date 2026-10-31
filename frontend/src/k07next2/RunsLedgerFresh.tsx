// K07NEXT2 M-R-UX-10: the fresh-project ledger screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readRunsLedgerDoc } from "./k07next2Api";
import type { RunsLedgerDoc } from "./k07next2Api";

export const RUNS_LEDGER_FRESH_PROJECT = "k07next2-fresh";

export function RunsLedgerFresh(): ReactElement {
  const [doc, setDoc] = useState<RunsLedgerDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readRunsLedgerDoc(RUNS_LEDGER_FRESH_PROJECT)
      .then((next) => {
        if (alive) {
          setDoc(next);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return (
    <section data-testid="k07next2-runs-ledger">
      <h2>{t("projects.runs.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.rows.length === 0 ? (
        <p>{t("ui.table.empty")}</p>
      ) : (
        <ol>
          {doc.rows.map((row) => (
            <li key={row.package_id}>
              {row.package_id} ({row.peak_concurrency})
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
