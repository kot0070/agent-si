// K07NEXT2 M-R-UX-6: the local models screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readLocalModelsDoc } from "./k07next2Api";
import type { LocalModelsDoc } from "./k07next2Api";

export function LocalModels(): ReactElement {
  const [doc, setDoc] = useState<LocalModelsDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readLocalModelsDoc()
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
    <section data-testid="k07next2-local-models">
      <h2>{t("settings.localbench.modelsTitle")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.length === 0 ? (
        <p>{t("settings.localbench.modelsEmpty")}</p>
      ) : (
        <ol>
          {doc.map((row) => (
            <li key={row.model}>
              {row.model} ({row.status})
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
