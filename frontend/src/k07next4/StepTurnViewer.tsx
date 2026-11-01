// K07NEXT4 MH-5: the step mode turn viewer.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readStepTurnDoc } from "./k07next4Api";
import type { StepTurnDoc } from "./k07next4Api";

export function StepTurnViewer(): ReactElement {
  const [doc, setDoc] = useState<StepTurnDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readStepTurnDoc(1)
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
    <section data-testid="k07next4-step-turn">
      <h2>{t("tasks.list.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <div>
          <p>{doc.model_input}</p>
          <p>{doc.observation}</p>
        </div>
      )}
    </section>
  );
}
