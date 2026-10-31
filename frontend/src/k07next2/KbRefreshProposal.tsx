// K07NEXT2 M-R-UX-9: the KB refresh proposal screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readKbProposalDoc } from "./k07next2Api";
import type { KbProposalDoc } from "./k07next2Api";

export function KbRefreshProposal(): ReactElement {
  const [doc, setDoc] = useState<KbProposalDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readKbProposalDoc()
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
    <section data-testid="k07next2-kb-proposal">
      <h2>{t("firstrun.optional.kbs")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.proposals.length === 0 ? (
        <p data-testid="k07next2-kb-proposal-empty">{t("ui.table.empty")}</p>
      ) : (
        <ol>
          {doc.proposals.map((proposal, index) => (
            <li key={index}>{JSON.stringify(proposal)}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
