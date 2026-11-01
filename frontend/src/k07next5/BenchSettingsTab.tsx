// K07NEXT5 R-341-UI: the benchmark settings tab with path scan,
// level estimate with duration, warnings plus per-model results.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readBenchTabDoc } from "./k07next5Api";
import type { BenchTabDoc } from "./k07next5Api";

export function BenchSettingsTab(): ReactElement {
  const [doc, setDoc] = useState<BenchTabDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readBenchTabDoc("k07next5-bench-b", "Quick", true)
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
  if (doc === null) {
    return (
      <section data-testid="k07next5-bench-tab-loading">
        <p>{t("chat.stream.spinner")}</p>
      </section>
    );
  }
  return (
    <section data-testid="k07next5-bench-tab">
      <h2>{t("settings.localbench.title")}</h2>
      <p>
        {doc.estimate.model_id} {doc.estimate.level}{" "}
        {doc.estimate.minutes_min}-{doc.estimate.minutes_max}
      </p>
      <ul>
        {doc.warnings.map((warning) => (
          <li key={warning.code}>{warning.code}</li>
        ))}
      </ul>
      <p>
        {t("settings.localbench.resultsTitle")}: {doc.results.length}
      </p>
    </section>
  );
}
