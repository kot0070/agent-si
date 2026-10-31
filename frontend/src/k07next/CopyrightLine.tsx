// K07NEXT M-P4-139: the copyright line screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readCopyright } from "./k07nextApi";
import type { CopyrightDoc } from "./k07nextApi";

export function CopyrightLine(): ReactElement {
  const [doc, setDoc] = useState<CopyrightDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readCopyright()
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
    <section data-testid="k07next-copyright">
      <h2>{t("about.thirdParty.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next-copyright-en">{doc.line_en}</p>
          <p data-testid="k07next-copyright-uk">{doc.line_uk}</p>
          <p>{t("about.licence.line")}</p>
        </>
      )}
    </section>
  );
}
