// K07NEXT4 LIVE0-08: the session token card.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { writeSessionTokenDoc } from "./k07next4Api";
import type { SessionWriteDoc } from "./k07next4Api";

export function SessionTokenCard(): ReactElement {
  const [doc, setDoc] = useState<SessionWriteDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void writeSessionTokenDoc()
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
    <section data-testid="k07next4-session-token">
      <h2>{t("chat.composer.send")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <p>{doc.actor}</p>
      )}
    </section>
  );
}
