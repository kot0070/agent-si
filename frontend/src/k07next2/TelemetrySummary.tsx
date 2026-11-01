// K07NEXT2 M-R-UX-8: the telemetry summary screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readTelemetryDoc } from "./k07next2Api";
import type { TelemetryDoc } from "./k07next2Api";

export function TelemetrySummary(): ReactElement {
  const [doc, setDoc] = useState<TelemetryDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readTelemetryDoc()
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
    <section data-testid="k07next2-telemetry">
      <h2>{t("projects.ai_usage.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <dl>
          <dt>{t("telemetry.tokens")}</dt>
          <dd data-testid="k07next2-telemetry-metric-records">
            {doc.metric_records}
          </dd>
          <dt>{t("telemetry.cost")}</dt>
          <dd data-testid="k07next2-telemetry-events">
            {doc.telemetry_events}
          </dd>
        </dl>
      )}
    </section>
  );
}
