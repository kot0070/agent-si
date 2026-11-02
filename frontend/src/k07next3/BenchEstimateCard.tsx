// K07NEXT3 LIVE0-02: the bench estimate card screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readBenchEstimateDoc } from "./k07next3Api";
import type { BenchEstimateDoc } from "./k07next3Api";

export const BENCH_ESTIMATE_MODEL = "k07next3-bench";
export const BENCH_ESTIMATE_LEVEL = "Quick";

export interface BenchEstimateCardProps {
  modelId?: string | null;
  level?: string;
}

export function BenchEstimateCard(props: BenchEstimateCardProps): ReactElement {
  const [doc, setDoc] = useState<BenchEstimateDoc | null>(null);
  // The estimate follows the model selected in the bench scan plus the
  // chosen level. An explicit null means none is selected: no estimate
  // line renders and no estimate route is read. Undefined keeps the
  // legacy seeded coordinates.
  const selected =
    props.modelId === undefined ? BENCH_ESTIMATE_MODEL : props.modelId;
  const level = props.level ?? BENCH_ESTIMATE_LEVEL;
  useEffect(() => {
    if (selected === null || selected === "") {
      setDoc(null);
      return;
    }
    let alive = true;
    void readBenchEstimateDoc(selected, level)
      .then((next) => {
        if (alive) {
          setDoc(next);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [selected, level]);
  return (
    <section data-testid="k07next3-bench-estimate">
      <h2>{t("settings.localAi.title")}</h2>
      {doc === null ? (
        selected === null || selected === "" ? (
          <p data-testid="k07next3-bench-estimate-empty">
            {t("empty.generic")}
          </p>
        ) : (
          <p>{t("chat.stream.spinner")}</p>
        )
      ) : (
        <>
          <p data-testid="k07next3-bench-estimate-value">{doc.model_id}</p>
          <p>{doc.level}</p>
        </>
      )}
    </section>
  );
}
