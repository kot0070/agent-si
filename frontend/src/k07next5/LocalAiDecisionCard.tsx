// K07NEXT5 111-UI: the local AI per-change decision record card.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { writeLocalAiDecisionDoc } from "./k07next5Api";
import type { LocalAiDecisionDoc } from "./k07next5Api";

export function LocalAiDecisionCard(): ReactElement {
  const [doc, setDoc] = useState<LocalAiDecisionDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void writeLocalAiDecisionDoc(
      "k07next5-b",
      { model_id: "k07next5-b-model" },
      "k07next5 adopt model",
      "k07next5 proof",
      "ui",
    )
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
    <section data-testid="k07next5-decision">
      <h2>{t("settings.localbench.decisionTitle")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <p>
          {doc.decision_id} {doc.config.model_id}
        </p>
      )}
    </section>
  );
}
