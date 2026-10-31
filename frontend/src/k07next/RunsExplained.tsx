// K07NEXT R-348: Runs versus code tests versus local tests, real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readRunsExplained } from "./k07nextApi";
import type { RunsExplainedDoc } from "./k07nextApi";

export function RunsExplained(): ReactElement {
  const [doc, setDoc] = useState<RunsExplainedDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readRunsExplained()
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
    <section data-testid="k07next-runs-explained">
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        doc.sections.map((section) => (
          <article key={section.key}>
            <h3>{t(`howItWorks.${section.key}.title`)}</h3>
            <p>{t(`howItWorks.${section.key}.body`)}</p>
          </article>
        ))
      )}
    </section>
  );
}
