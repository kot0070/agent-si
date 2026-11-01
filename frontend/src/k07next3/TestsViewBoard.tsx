// K07NEXT3 LIVE0-05: the tests view board screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readTestsViewDoc } from "./k07next3Api";
import type { TestsViewDoc } from "./k07next3Api";

export const TESTS_VIEW_PLAN = "k07next3";
export const TESTS_VIEW_RUN = "seed";

export function TestsViewBoard(): ReactElement {
  const [doc, setDoc] = useState<TestsViewDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readTestsViewDoc(TESTS_VIEW_PLAN, TESTS_VIEW_RUN)
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
    <section data-testid="k07next3-tests-view">
      <h2>{t("settings.localAi.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next3-tests-view-value">{doc.plan_id}</p>
          <p>{doc.run_id}</p>
        </>
      )}
    </section>
  );
}
