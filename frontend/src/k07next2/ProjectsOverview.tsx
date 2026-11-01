// K07NEXT2 M-R-UX-3: the project overview screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readProjectsDoc } from "./k07next2Api";
import type { ProjectsDoc } from "./k07next2Api";

export function ProjectsOverview(): ReactElement {
  const [doc, setDoc] = useState<ProjectsDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readProjectsDoc()
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
    <section data-testid="k07next2-projects">
      <h2>{t("projects.list.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.projects.length === 0 ? (
        <p>{t("projects.list.empty")}</p>
      ) : (
        <ol>
          {doc.projects.map((project) => (
            <li key={project.project_id}>{project.name}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
