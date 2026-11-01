// K07NEXT R-319: the newcomer start guide screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readNewcomerGuide } from "./k07nextApi";
import type { NewcomerGuideDoc } from "./k07nextApi";

export function NewcomerGuide(): ReactElement {
  const [guide, setGuide] = useState<NewcomerGuideDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readNewcomerGuide()
      .then((next) => {
        if (alive) {
          setGuide(next);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return (
    <section data-testid="k07next-newcomer-guide">
      <h2>{t("firstrun.title")}</h2>
      {guide === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <ol>
          {guide.steps.map((step) => (
            <li key={step.id}>{t(`firstrun.steps.${step.id}`)}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
