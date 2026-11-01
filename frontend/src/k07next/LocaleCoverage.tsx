// K07NEXT R-362: locale coverage in both languages, real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readLocaleCoverage } from "./k07nextApi";
import type { LocaleCoverageDoc } from "./k07nextApi";

export function LocaleCoverage(): ReactElement {
  const [doc, setDoc] = useState<LocaleCoverageDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readLocaleCoverage()
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
    <section data-testid="k07next-locale-coverage">
      <h2>{t("settings.general.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next-locale-counts">
            {doc.en_leaves}:{doc.uk_leaves}
          </p>
          <p data-testid="k07next-locale-parity">
            {doc.parity ? "true" : "false"}
          </p>
          <p>{t("empty.generic")}</p>
        </>
      )}
    </section>
  );
}
