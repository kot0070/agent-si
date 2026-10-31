// K07NEXT3 B0B-UNCOVERED_MVP_ACCEPT-178: the agents live overview screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readAgentsLiveDoc } from "./k07next3Api";
import type { AgentsLiveDoc } from "./k07next3Api";

export function AgentsLiveOverview(): ReactElement {
  const [doc, setDoc] = useState<AgentsLiveDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readAgentsLiveDoc()
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
    <section data-testid="k07next3-agents-live">
      <h2>{t("projects.list.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.agents.length === 0 ? (
        <p>{t("projects.list.empty")}</p>
      ) : (
        <ol>
          {doc.agents.map((row) => (
            <li key={`${row.agent}:${row.scope}`}>
              {row.agent} {row.status}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
