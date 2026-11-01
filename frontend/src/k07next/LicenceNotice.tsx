// K07NEXT R-342: the licence notice screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readLicence } from "./k07nextApi";
import type { LicenceDoc } from "./k07nextApi";

export function LicenceNotice(): ReactElement {
  const [doc, setDoc] = useState<LicenceDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readLicence()
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
    <section data-testid="k07next-licence">
      <h2>{t("about.thirdParty.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next-licence-line">{doc.licence_line}</p>
          <p>{t(doc.mit_ref)}</p>
          <p>{t(doc.third_party_title_ref)}</p>
        </>
      )}
    </section>
  );
}
