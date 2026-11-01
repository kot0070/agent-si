// K07NEXT4 MH-6: the turn triple board with the budget counter.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readTurnTripleDoc } from "./k07next4Api";
import type { TurnTripleDoc } from "./k07next4Api";

export function TurnTripleBoard(): ReactElement {
  const [doc, setDoc] = useState<TurnTripleDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readTurnTripleDoc()
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
    <section data-testid="k07next4-turn-triple">
      <h2>{t("agents.live.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <div>
          <ol>
            {doc.turns.map((triple) => (
              <li key={triple.plan}>
                <p>{triple.plan}</p>
                <p>{triple.action}</p>
                <p>{triple.observation}</p>
              </li>
            ))}
          </ol>
          <p>
            {doc.used}/{doc.limit}
          </p>
        </div>
      )}
    </section>
  );
}
