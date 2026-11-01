// K07NEXT2 M-R-UX-4: the local runtime status screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readLocalStatusDoc } from "./k07next2Api";
import type { LocalStatusDoc } from "./k07next2Api";

export function LocalRuntimeStatus(): ReactElement {
  const [doc, setDoc] = useState<LocalStatusDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readLocalStatusDoc()
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
    <section data-testid="k07next2-local-status">
      <h2>{t("settings.localAi.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next2-local-status-value">{doc.status}</p>
          <p>{doc.reason}</p>
        </>
      )}
    </section>
  );
}
