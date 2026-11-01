// FXTESTSUI Tests tab: served counters plus one row per test from the
// merged teststage read routes (latest plan + run by project, tests-view,
// result output). Every number renders the served value verbatim; rows
// show the served name, kind in plain words, status, and the served
// reason only when one is recorded (BLOCKED rows require one at write
// time). Output text opens lazily per row. No run reads back as an empty
// state naming how a run starts. The tab holds zero settings controls:
// the single local-tests switch lives in the settings area by
// ProjectLimitsSection, never here. All labels are inline English (lane
// paperwork staged no label keys; locale files are owned by FXLAYOUT).
// Live refresh: while the served view reports remaining work, the view
// re-reads on a short interval; a finished run stops polling.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import {
  readLatestPlan,
  readLatestRun,
  readResultOutput,
  readTestsView,
  testKindLabel,
} from "./projectsApi";
import type { TestsView } from "./projectsApi";

export interface TestsTabProps {
  projectId: string;
}

const TESTS_POLL_MS = 5000;

interface TestsFailure {
  errorKey: string;
  code: string;
}

function toTestsFailure(error: unknown): TestsFailure {
  if (error instanceof ApiError) {
    return { errorKey: apiErrorLocaleKey(error.code), code: error.code };
  }
  return { errorKey: "errors.generic", code: "CONTEXT_MISSING" };
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function TestsTab(props: TestsTabProps): ReactElement {
  const [phase, setPhase] = useState<
    | { kind: "loading" }
    | { kind: "empty" }
    | { kind: "ready"; view: TestsView }
    | { kind: "failed"; failure: TestsFailure }
  >({ kind: "loading" });
  const [nonce, setNonce] = useState(0);
  const [outputs, setOutputs] = useState<Record<string, string>>({});
  const [opening, setOpening] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const plan = await readLatestPlan(props.projectId);
        const run = await readLatestRun(props.projectId);
        const view = await readTestsView(plan.plan_id, run.run_id);
        if (alive) {
          setPhase({ kind: "ready", view });
        }
      } catch (error) {
        if (!alive) {
          return;
        }
        if (isNotFound(error)) {
          setPhase({ kind: "empty" });
        } else {
          setPhase({ kind: "failed", failure: toTestsFailure(error) });
        }
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [props.projectId, nonce]);

  // Live refresh while the served view reports remaining work.
  const unfinished =
    phase.kind === "ready" ? phase.view.remaining > 0 : false;
  const readyPlanId = phase.kind === "ready" ? phase.view.plan_id : null;
  const readyRunId = phase.kind === "ready" ? phase.view.run_id : null;
  useEffect(() => {
    if (!unfinished || readyPlanId === null || readyRunId === null) {
      return;
    }
    const timer = setInterval(() => {
      void readTestsView(readyPlanId, readyRunId).then(
        (view) => {
          setPhase({ kind: "ready", view });
        },
        () => undefined,
      );
    }, TESTS_POLL_MS);
    return () => {
      clearInterval(timer);
    };
  }, [unfinished, readyPlanId, readyRunId]);

  async function openOutput(testId: string, ref: string): Promise<void> {
    setOpening((prev) => ({ ...prev, [testId]: true }));
    try {
      const answer = await readResultOutput(ref);
      setOutputs((prev) => ({ ...prev, [testId]: answer.output }));
    } catch {
      setOutputs((prev) => ({ ...prev, [testId]: "" }));
    } finally {
      setOpening((prev) => ({ ...prev, [testId]: false }));
    }
  }

  function retry(): void {
    setNonce((value) => value + 1);
  }

  return (
    <section data-testid="tests-tab">
      <h2>Tests</h2>
      <p data-testid="tests-explainer">
        A run is one agent working on one task; code tests are the
        project&apos;s own suite; local tests are catalog checks this machine
        runs before spend. This tab shows the latest run: served counters and
        one row per test. It never changes settings.
      </p>
      {phase.kind === "loading" ? (
        <LoadingState loadingKey="ui.loading.more" />
      ) : phase.kind === "empty" ? (
        <div data-testid="tests-empty">
          <EmptyState
            stateKey="ui.table.empty"
            actionKey={null}
            onAction={null}
          />
          <p data-testid="tests-empty-how">
            No test run has started for this project yet. A run starts with
            POST /api/v1/teststage/runs/start for the latest plan, then this
            tab shows counters and one row per test.
          </p>
        </div>
      ) : phase.kind === "failed" ? (
        <div data-testid="tests-error">
          <ErrorPanel
            errorKey={phase.failure.errorKey}
            code={phase.failure.code}
            onRetry={retry}
          />
        </div>
      ) : (
        <div>
          <div data-testid="tests-counters">
            <span>active</span>
            <span data-testid="tests-counters-active">{phase.view.active}</span>
            <span>passed</span>
            <span data-testid="tests-counters-passed">{phase.view.passed}</span>
            <span>remaining</span>
            <span data-testid="tests-counters-remaining">
              {phase.view.remaining}
            </span>
          </div>
          <ul>
            {phase.view.rows.map((row) => (
              <li key={row.test_id} data-testid={`tests-row-${row.test_id}`}>
                <span data-testid={`tests-name-${row.test_id}`}>
                  {row.test_id}
                </span>
                <span data-testid={`tests-kind-${row.test_id}`}>
                  {testKindLabel(row.kind)}
                </span>
                <span data-testid={`tests-status-${row.test_id}`}>
                  {row.status}
                </span>
                {row.reason !== undefined &&
                row.reason !== null &&
                row.reason !== "" ? (
                  <span data-testid={`tests-reason-${row.test_id}`}>
                    {row.reason}
                  </span>
                ) : null}
                {row.output_ref !== null ? (
                  <button
                    type="button"
                    data-testid={`tests-output-${row.test_id}`}
                    disabled={opening[row.test_id] === true}
                    onClick={() => {
                      if (outputs[row.test_id] === undefined) {
                        void openOutput(row.test_id, row.output_ref as string);
                      } else {
                        setOutputs((prev) => {
                          const next = { ...prev };
                          delete next[row.test_id];
                          return next;
                        });
                      }
                    }}
                  >
                    {outputs[row.test_id] === undefined
                      ? "Show output"
                      : "Hide output"}
                  </button>
                ) : null}
                {outputs[row.test_id] !== undefined ? (
                  <pre data-testid={`tests-output-text-${row.test_id}`}>
                    {outputs[row.test_id]}
                  </pre>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
