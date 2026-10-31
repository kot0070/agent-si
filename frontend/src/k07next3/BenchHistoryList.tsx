// K07NEXT3 LIVE0-03: the bench history list screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readBenchHistoryDoc } from "./k07next3Api";
import type { BenchHistoryDoc } from "./k07next3Api";

export function BenchHistoryList(): ReactElement {
  const [doc, setDoc] = useState<BenchHistoryDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readBenchHistoryDoc()
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
    <section data-testid="k07next3-bench-history">
      <h2>{t("projects.list.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.length === 0 ? (
        <p>{t("projects.list.empty")}</p>
      ) : (
        <ol>
          {doc.map((runId) => (
            <li key={runId}>{runId}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
