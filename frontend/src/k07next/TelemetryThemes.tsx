// K07NEXT M-P3-92: telemetry themes screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readTelemetryThemes } from "./k07nextApi";
import type { TelemetryThemesDoc } from "./k07nextApi";

export function TelemetryThemes(): ReactElement {
  const [doc, setDoc] = useState<TelemetryThemesDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readTelemetryThemes()
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
    <section data-testid="k07next-telemetry-themes">
      <h2>{t("settings.appearance.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next-telemetry-list">{doc.themes.join(",")}</p>
          <p>{t(doc.tokens_key)}</p>
          <p>{t(doc.cost_key)}</p>
        </>
      )}
    </section>
  );
}
