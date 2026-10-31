// K07NEXT5 B0B-UNCOVERED_ARCH-526: the stored Local AI config view
// with endpoint plus models.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readLocalAiSettingsViewDoc } from "./k07next5Api";
import type { LocalAiSettingsViewDoc } from "./k07next5Api";

export function LocalAiViewCard(): ReactElement {
  const [doc, setDoc] = useState<LocalAiSettingsViewDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readLocalAiSettingsViewDoc("proj-a")
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
  if (doc === null) {
    return (
      <section data-testid="k07next5-local-ai-view-loading">
        <p>{t("chat.stream.spinner")}</p>
      </section>
    );
  }
  return (
    <section data-testid="k07next5-local-ai-view">
      <h2>{t("settings.localAi.title")}</h2>
      <p>{doc.config.endpoint_url}</p>
      <p>{doc.config.model_id}</p>
    </section>
  );
}
