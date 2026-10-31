// K07NEXT5 B0B-UNCOVERED_MVP_ACCEPT-199: the outage fixture card
// asserting the provider health transitions.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readProviderHealthTransitionsDoc } from "./k07next5Api";
import type { ProviderHealthTransitionsDoc } from "./k07next5Api";

export function ProviderOutageCard(): ReactElement {
  const [doc, setDoc] = useState<ProviderHealthTransitionsDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readProviderHealthTransitionsDoc()
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
    <section data-testid="k07next5-provider-outage">
      <h2>{t("chat.stream.offline")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <p>{doc.transitions.join(" ")}</p>
      )}
    </section>
  );
}
