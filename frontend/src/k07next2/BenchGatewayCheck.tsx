// K07NEXT2 M-R-UX-12: the bench gateway check screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readBenchCheckDoc } from "./k07next2Api";
import type { BenchCheckDoc } from "./k07next2Api";

export function BenchGatewayCheck(): ReactElement {
  const [doc, setDoc] = useState<BenchCheckDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readBenchCheckDoc()
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
    <section data-testid="k07next2-bench-check">
      <h2>{t("settings.localbench.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next2-bench-check-reachable">
            {String(doc.reachable)}
          </p>
          <p>{doc.reason}</p>
        </>
      )}
    </section>
  );
}
