// K07NEXT4 LIVE0B-01: the projects list with Add Project inline.
import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { createProjectsDoc, readProjectsDoc } from "./k07next4Api";

export function ProjectsLiveList(): ReactElement {
  const [names, setNames] = useState<string[] | null>(null);
  const [draft, setDraft] = useState("k07next4-new");
  const refresh = useCallback(() => {
    void readProjectsDoc()
      .then((next) => {
        setNames(next.projects.map((row) => row.name));
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  async function addProject(): Promise<void> {
    await createProjectsDoc(draft, "f-k07next4").catch(() => undefined);
    refresh();
  }
  return (
    <section data-testid="k07next4-projects-live">
      <h2>{t("projects.list.title")}</h2>
      {names === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : names.length === 0 ? (
        <p>{t("projects.list.empty")}</p>
      ) : (
        <ol>
          {names.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ol>
      )}
      <input
        aria-label={t("projects.list.title")}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
      />
      <button type="button" onClick={() => void addProject()}>
        {t("tasks.creator.create")}
      </button>
    </section>
  );
}
