// K07NEXT4 LIVE0B-04: the console page shell with title plus styling.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readPageShellDoc } from "./k07next4Api";
import type { PageShellDoc } from "./k07next4Api";

export function ConsolePageShell(): ReactElement {
  const [doc, setDoc] = useState<PageShellDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readPageShellDoc()
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
      <section data-testid="k07next4-page-shell-loading">
        <p>{t("chat.stream.spinner")}</p>
      </section>
    );
  }
  return (
    <div className={doc.console_class} data-testid="k07next4-page-shell">
      <h1>{t("shell.sidebar.projects")}</h1>
      <p>{doc.title}</p>
    </div>
  );
}
