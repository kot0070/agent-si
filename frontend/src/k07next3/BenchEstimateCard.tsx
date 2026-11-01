// K07NEXT3 LIVE0-02: the bench estimate card screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readBenchEstimateDoc } from "./k07next3Api";
import type { BenchEstimateDoc } from "./k07next3Api";

export const BENCH_ESTIMATE_MODEL = "k07next3-bench";

export function BenchEstimateCard(): ReactElement {
  const [doc, setDoc] = useState<BenchEstimateDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readBenchEstimateDoc(BENCH_ESTIMATE_MODEL)
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
    <section data-testid="k07next3-bench-estimate">
      <h2>{t("settings.localAi.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next3-bench-estimate-value">{doc.model_id}</p>
          <p>{doc.level}</p>
        </>
      )}
    </section>
  );
}
