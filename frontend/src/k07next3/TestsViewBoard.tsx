// K07NEXT3 LIVE0-05: the tests view board screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError } from "../api/errors";
import { t } from "../locale/index";
import { readTestsViewDoc } from "./k07next3Api";
import type { TestsViewDoc } from "./k07next3Api";
import { readLatestPlan, readLatestRun } from "../projects/projectsApi";

export const TESTS_VIEW_PLAN = "k07next3";
export const TESTS_VIEW_RUN = "seed";

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export interface TestsViewBoardProps {
  projectId?: string;
}

export function TestsViewBoard(props: TestsViewBoardProps): ReactElement {
  const [doc, setDoc] = useState<TestsViewDoc | null>(null);
  const [empty, setEmpty] = useState(false);
  useEffect(() => {
    let alive = true;
    setDoc(null);
    setEmpty(false);
    async function load(): Promise<void> {
      try {
        let planId = TESTS_VIEW_PLAN;
        let runId = TESTS_VIEW_RUN;
        if (props.projectId !== undefined) {
          const plan = await readLatestPlan(props.projectId);
          const run = await readLatestRun(props.projectId);
          planId = plan.plan_id;
          runId = run.run_id;
        }
        const next = await readTestsViewDoc(planId, runId);
        if (alive) {
          setDoc(next);
        }
      } catch (error) {
        if (!alive) {
          return;
        }
        if (isNotFound(error)) {
          setEmpty(true);
        } else {
          setEmpty(false);
        }
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [props.projectId]);
  if (empty) {
    return (
      <section data-testid="k07next3-tests-view">
        <h2>{t("settings.localAi.title")}</h2>
        <p data-testid="k07next3-tests-view-empty">{t("empty.generic")}</p>
      </section>
    );
  }
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
