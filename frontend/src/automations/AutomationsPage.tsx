// FXAUTO automations screen: one page under Settings > Watcher and
// automations. Every row is a served record (rules, runs, templates,
// checkpoints, approvals); the page never computes automation state.
// Compact card rows in the WatcherTab spacing style.
import { useEffect, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { t, formatScreenTime } from "../locale/index";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import "./automations.css";
import {
  createAutomationRule,
  decideAutomationApproval,
  listAutomationApprovals,
  listAutomationCheckpoints,
  listAutomationRules,
  listAutomationRuns,
  listAutomationTemplates,
  readGlobalPause,
  readProjectPause,
  resumeAutomationCheckpoint,
  runAutomationRuleNow,
  setAutomationRuleEnabled,
  setGlobalPause,
  setProjectPause,
  type AutomationApproval,
  type AutomationCheckpoint,
  type AutomationResult,
  type AutomationRule,
  type AutomationRunRow,
  type AutomationTemplate,
  type BuilderDraft,
  type RuleDraft,
} from "./automationsApi";

export type WhenKind = "schedule" | "metric" | "event";

const WHEN_DETAILS: Record<WhenKind, string[]> = {
  schedule: ["every-3h", "every-30m", "daily-22:00"],
  metric: ["budget-90", "context-70", "turns-40"],
  event: ["app-started", "audit-finished", "audit-failed"],
};

const WHEN_KEY: Record<string, string> = {
  "every-3h": "fxauto.when.every3h",
  "every-30m": "fxauto.when.every30m",
  "daily-2200": "fxauto.when.daily2200",
  "budget-90": "fxauto.when.budget90",
  "context-70": "fxauto.when.context70",
  "turns-40": "fxauto.when.turns40",
  "app-started": "fxauto.when.appStarted",
  "audit-finished": "fxauto.when.auditFinished",
  "audit-failed": "fxauto.when.auditFailed",
};

const DO_OPTIONS = [
  "start-next-task",
  "reread-context",
  "checkpoint",
  "pause-project",
  "switch-model",
  "run-audit",
  "notify",
];

const DO_KEY: Record<string, string> = {
  "start-next-task": "fxauto.do.startNextTask",
  "reread-context": "fxauto.do.rereadContext",
  checkpoint: "fxauto.do.checkpoint",
  "pause-project": "fxauto.do.pauseProject",
  "switch-model": "fxauto.do.switchModel",
  "run-audit": "fxauto.do.runAudit",
  notify: "fxauto.do.notify",
};

const STRONG_DO = new Set([
  "pause-project",
  "start-next-task",
  "switch-model",
  "run-audit",
]);

function whenText(whenKind: string, whenDetail: string): string {
  const key = WHEN_KEY[whenDetail];
  return key === undefined ? whenDetail : t(key);
}

function doText(doAction: string): string {
  const key = DO_KEY[doAction];
  return key === undefined ? doAction : t(key);
}

/** One plain sentence saying what a rule does (name + when + do). */
export function ruleSentence(rule: {
  name: string;
  when_kind: string;
  when_detail: string;
  do: string;
}): string {
  return t("fxauto.ruleSentence", {
    name: rule.name,
    when: whenText(rule.when_kind, rule.when_detail),
    do: doText(rule.do),
  });
}

function resultParams(
  result: AutomationResult,
): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  const params = result.params ?? {};
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string" || typeof value === "number") {
      out[key] = value === -1 ? "-" : value;
    } else if (value !== null && value !== undefined) {
      out[key] = String(value);
    }
  }
  return out;
}

/** Plain localized result sentence; never a code. */
export function resultText(result: AutomationResult): string {
  return t(result.key, resultParams(result));
}

interface PageData {
  rules: AutomationRule[];
  runs: AutomationRunRow[];
  templates: AutomationTemplate[];
  checkpoints: AutomationCheckpoint[];
  latest: AutomationCheckpoint | null;
  approvals: AutomationApproval[];
}

async function loadPage(projectId: string | null): Promise<PageData> {
  const templates = await listAutomationTemplates();
  if (projectId === null) {
    return {
      rules: [],
      runs: [],
      templates,
      checkpoints: [],
      latest: null,
      approvals: [],
    };
  }
  const [rules, runs, stored, approvals] = await Promise.all([
    listAutomationRules(projectId),
    listAutomationRuns(projectId),
    listAutomationCheckpoints(projectId),
    listAutomationApprovals(projectId),
  ]);
  return {
    rules,
    runs,
    templates,
    checkpoints: stored.checkpoints,
    latest: stored.latest,
    approvals,
  };
}

function toFailure(error: unknown): { errorKey: string; code: string } {
  if (error instanceof ApiError) {
    return { errorKey: apiErrorLocaleKey(error.code), code: error.code };
  }
  return { errorKey: "errors.generic", code: "CONTEXT_MISSING" };
}

export function AutomationsPage(props: {
  projectId: string | null;
}): ReactElement {
  const projectId = props.projectId;
  const [data, setData] = useState<PageData | null>(null);
  const [globalStopped, setGlobalStopped] = useState<boolean | null>(null);
  const [projectStopped, setProjectStopped] = useState<boolean | null>(null);
  const [failure, setFailure] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [draft, setDraft] = useState<RuleDraft>({
    name: "",
    when_kind: "schedule",
    when_detail: "every-30m",
    if_text: "",
    do: "notify",
    miss: "once",
  });
  const [builderMessage, setBuilderMessage] = useState<string | null>(null);
  const [runResults, setRunResults] = useState<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const [page, global, project] = await Promise.all([
          loadPage(projectId),
          readGlobalPause(),
          projectId === null
            ? Promise.resolve(null)
            : readProjectPause(projectId),
        ]);
        if (alive) {
          setData(page);
          setGlobalStopped(global);
          setProjectStopped(project);
          setFailure(null);
        }
      } catch (error) {
        if (alive) {
          setFailure(toFailure(error));
        }
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [projectId, nonce]);

  function refresh(): void {
    setNonce((value) => value + 1);
  }

  async function flipGlobal(next: boolean): Promise<void> {
    try {
      await setGlobalPause(next, next ? "user stop switch" : "");
      setGlobalStopped(next);
      setNotice(null);
    } catch (error) {
      setFailure(toFailure(error));
    }
  }

  async function flipProject(next: boolean): Promise<void> {
    if (projectId === null) {
      return;
    }
    try {
      await setProjectPause(projectId, next);
      setProjectStopped(next);
      setNotice(null);
    } catch (error) {
      setFailure(toFailure(error));
    }
  }

  async function flipRule(rule: AutomationRule, next: boolean): Promise<void> {
    try {
      await setAutomationRuleEnabled(rule.project_id, rule.rule_id, next);
      refresh();
    } catch (error) {
      setFailure(toFailure(error));
    }
  }

  async function runNow(rule: AutomationRule): Promise<void> {
    setNotice(null);
    try {
      const receipt = await runAutomationRuleNow(
        rule.project_id,
        rule.rule_id,
      );
      setRunResults((prev) => ({
        ...prev,
        [rule.rule_id]: resultText(receipt.result),
      }));
      refresh();
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.code as string) === "AUTOMATION_PAUSED"
      ) {
        const detail = error.details?.message ?? "";
        setRunResults((prev) => ({
          ...prev,
          [rule.rule_id]: detail.includes("turned off")
            ? t("fxauto.turnedOffRefused")
            : t("fxauto.pausedRefused"),
        }));
        return;
      }
      setFailure(toFailure(error));
    }
  }

  async function decide(
    approval: AutomationApproval,
    approved: boolean,
  ): Promise<void> {
    try {
      await decideAutomationApproval(
        approval.project_id,
        approval.approval_id,
        approved,
      );
      refresh();
    } catch (error) {
      setFailure(toFailure(error));
    }
  }

  async function resume(checkpoint: AutomationCheckpoint): Promise<void> {
    if (projectId === null) {
      return;
    }
    try {
      await resumeAutomationCheckpoint(projectId, checkpoint.checkpoint_id);
      setNotice(resultText({
        key: "fxauto.results.unknown",
        params: {},
      }));
      refresh();
    } catch (error) {
      setFailure(toFailure(error));
    }
  }

  function openBuilder(prefill: BuilderDraft, name: string): void {
    const kind = prefill.when_kind as WhenKind;
    const details = WHEN_DETAILS[kind] ?? WHEN_DETAILS.schedule;
    setDraft({
      name,
      when_kind: prefill.when_kind,
      when_detail: details.includes(prefill.when_detail)
        ? prefill.when_detail
        : details[0] ?? "every-30m",
      if_text: prefill.if_text,
      do: DO_OPTIONS.includes(prefill.do) ? prefill.do : "notify",
      miss: prefill.miss === "skip" ? "skip" : "once",
    });
    setBuilderMessage(null);
    setBuilderOpen(true);
  }

  function validateDraft(candidate: RuleDraft): string | null {
    if (candidate.name.trim() === "") {
      return t("fxauto.builderNameRequired");
    }
    if (candidate.if_text.length > 500) {
      return t("fxauto.builderIfTooLong");
    }
    return null;
  }

  async function saveDraft(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (projectId === null) {
      return;
    }
    const problem = validateDraft(draft);
    if (problem !== null) {
      setBuilderMessage(problem);
      return;
    }
    try {
      await createAutomationRule(projectId, draft);
      setBuilderOpen(false);
      setBuilderMessage(null);
      refresh();
    } catch (error) {
      if (error instanceof ApiError) {
        setBuilderMessage(error.details?.message ?? error.code);
        return;
      }
      setBuilderMessage(t("errors.generic"));
    }
  }

  if (failure !== null) {
    return (
      <section data-testid="automations-page">
        <p>{t("fxauto.purpose")}</p>
        <ErrorPanel
          errorKey={failure.errorKey}
          code={failure.code}
          onRetry={refresh}
        />
      </section>
    );
  }
  if (data === null || globalStopped === null) {
    return (
      <section data-testid="automations-page">
        <p>{t("fxauto.purpose")}</p>
        <LoadingState loadingKey="ui.loading.more" />
      </section>
    );
  }

  const kind = draft.when_kind as WhenKind;
  const detailOptions = WHEN_DETAILS[kind] ?? WHEN_DETAILS.schedule;
  const preview: RuleDraft = {
    ...draft,
    name: draft.name.trim() === "" ? "…" : draft.name.trim(),
  };

  return (
    <section data-testid="automations-page">
      <p>{t("fxauto.purpose")}</p>
      <label>
        {t("fxauto.globalStop")}
        <input
          data-testid="auto-global-stop"
          type="checkbox"
          checked={globalStopped}
          onChange={(event) => {
            void flipGlobal(event.target.checked);
          }}
        />
        <span data-testid="auto-global-stop-state">
          {globalStopped ? t("fxauto.on") : t("fxauto.off")}
        </span>
      </label>
      {projectId === null ? null : (
        <label>
          {t("fxauto.projectStop")}
          <input
            data-testid="auto-project-stop"
            type="checkbox"
            checked={projectStopped ?? false}
            onChange={(event) => {
              void flipProject(event.target.checked);
            }}
          />
          <span data-testid="auto-project-stop-state">
            {projectStopped === true ? t("fxauto.on") : t("fxauto.off")}
          </span>
        </label>
      )}
      {notice === null ? null : (
        <p data-testid="auto-notice">{notice}</p>
      )}

      <h3 data-testid="auto-rules-title">{t("fxauto.rulesTitle")}</h3>
      {projectId === null ? (
        <p data-testid="auto-need-project">{t("fxauto.needProject")}</p>
      ) : data.rules.length === 0 ? (
        <div data-testid="auto-rules-empty">
          <p>{t("fxauto.rulesEmpty")}</p>
          <a href="#auto-templates">
            <button
              type="button"
              data-testid="auto-goto-templates"
            >
              {t("fxauto.templatesButton")}
            </button>
          </a>
          <button
            type="button"
            data-testid="auto-new-rule"
            onClick={() => {
              openBuilder(
                {
                  when_kind: "schedule",
                  when_detail: "every-30m",
                  if_text: "",
                  do: "notify",
                  miss: "once",
                },
                "",
              );
            }}
          >
            {t("fxauto.newRule")}
          </button>
        </div>
      ) : (
        <div data-testid="auto-rules">
          {data.rules.map((rule) => (
            <section
              key={rule.rule_id}
              data-testid={`auto-rule-${rule.rule_id}`}
              className="fxauto-card"
            >
              <h4>{rule.name}</h4>
              <p data-testid={`auto-rule-${rule.rule_id}-sentence`}>
                {ruleSentence(rule)}
              </p>
              <p data-testid={`auto-rule-${rule.rule_id}-next`}>
                {rule.next_run_at === null
                  ? t("fxauto.noNextRun")
                  : t("fxauto.nextRun", {
                      when: formatScreenTime(rule.next_run_at),
                    })}
              </p>
              <p>
                {t("fxauto.state")}:{" "}
                {rule.enabled ? t("fxauto.on") : t("fxauto.off")}
              </p>
              <label>
                {t("fxauto.state")}
                <input
                  data-testid={`auto-rule-${rule.rule_id}-enabled`}
                  type="checkbox"
                  checked={rule.enabled}
                  onChange={(event) => {
                    void flipRule(rule, event.target.checked);
                  }}
                />
              </label>
              <button
                type="button"
                data-testid={`auto-rule-${rule.rule_id}-run`}
                disabled={!rule.enabled}
                title={
                  rule.enabled ? undefined : t("fxauto.turnedOffRefused")
                }
                onClick={() => {
                  void runNow(rule);
                }}
              >
                {t("fxauto.runNow")}
              </button>
              {runResults[rule.rule_id] === undefined ? null : (
                <p data-testid={`auto-rule-${rule.rule_id}-result`}>
                  {runResults[rule.rule_id]}
                </p>
              )}
            </section>
          ))}
        </div>
      )}

      <h3 id="auto-templates" data-testid="auto-templates-title">
        {t("fxauto.templatesTitle")}
      </h3>
      <div data-testid="auto-templates">
        {data.templates.map((template) => (
          <section
            key={template.template_id}
            data-testid={`auto-template-${template.template_id}`}
            className="fxauto-card"
          >
            <h4>{template.name}</h4>
            <p>{template.description}</p>
            <p>
              <span
                data-testid={`auto-template-${template.template_id}-trigger`}
              >
                {t(template.trigger_key)}
              </span>{" "}
              ·{" "}
              <span
                data-testid={`auto-template-${template.template_id}-action`}
              >
                {t(template.action_key)}
              </span>
            </p>
            <button
              type="button"
              data-testid={`auto-template-${template.template_id}-use`}
              disabled={projectId === null}
              onClick={() => {
                openBuilder(template.draft, template.name);
              }}
            >
              {t("fxauto.templateUse")}
            </button>
          </section>
        ))}
      </div>

      {builderOpen && projectId !== null ? (
        <form data-testid="auto-builder" onSubmit={(event) => {
          void saveDraft(event);
        }}>
          <h4>{t("fxauto.builderTitle")}</h4>
          <label>
            {t("fxauto.builderName")}
            <input
              data-testid="auto-builder-name"
              type="text"
              value={draft.name}
              onChange={(event) => {
                setDraft({ ...draft, name: event.target.value });
              }}
            />
          </label>
          <label>
            {t("fxauto.builderWhen")}
            <select
              data-testid="auto-builder-when-kind"
              value={draft.when_kind}
              onChange={(event) => {
                const nextKind = event.target.value as WhenKind;
                const nextDetails = WHEN_DETAILS[nextKind] ??
                  WHEN_DETAILS.schedule;
                setDraft({
                  ...draft,
                  when_kind: nextKind,
                  when_detail: nextDetails[0] ?? "every-30m",
                });
              }}
            >
              {(Object.keys(WHEN_DETAILS) as WhenKind[]).map((option) => (
                <option key={option} value={option}>
                  {option === "schedule"
                    ? t("fxauto.whenSchedule")
                    : option === "metric"
                      ? t("fxauto.whenMetric")
                      : t("fxauto.whenEvent")}
                </option>
              ))}
            </select>
            <select
              data-testid="auto-builder-when-detail"
              value={draft.when_detail}
              onChange={(event) => {
                setDraft({ ...draft, when_detail: event.target.value });
              }}
            >
              {detailOptions.map((option) => (
                <option key={option} value={option}>
                  {whenText(draft.when_kind, option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("fxauto.builderIf")}
            <input
              data-testid="auto-builder-if"
              type="text"
              value={draft.if_text}
              onChange={(event) => {
                setDraft({ ...draft, if_text: event.target.value });
              }}
            />
          </label>
          <label>
            {t("fxauto.builderDo")}
            <select
              data-testid="auto-builder-do"
              value={draft.do}
              onChange={(event) => {
                setDraft({ ...draft, do: event.target.value });
              }}
            >
              {DO_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {doText(option)}
                </option>
              ))}
            </select>
          </label>
          {STRONG_DO.has(draft.do) ? (
            <p data-testid="auto-builder-strong-note">
              {t("fxauto.builderStrongNote")}
            </p>
          ) : null}
          <label>
            {t("fxauto.builderMiss")}
            <select
              data-testid="auto-builder-miss"
              value={draft.miss}
              onChange={(event) => {
                setDraft({ ...draft, miss: event.target.value });
              }}
            >
              <option value="skip">{t("fxauto.missSkip")}</option>
              <option value="once">{t("fxauto.missOnce")}</option>
            </select>
          </label>
          <p data-testid="auto-builder-preview">{ruleSentence(preview)}</p>
          <button
            type="button"
            data-testid="auto-builder-validate"
            onClick={() => {
              const problem = validateDraft(draft);
              setBuilderMessage(problem ?? t("fxauto.builderValid"));
            }}
          >
            {t("fxauto.builderValidate")}
          </button>
          {builderMessage === null ? null : (
            <p data-testid="auto-builder-message">{builderMessage}</p>
          )}
          <button type="submit" data-testid="auto-builder-save">
            {t("fxauto.builderSave")}
          </button>
          <button
            type="button"
            data-testid="auto-builder-cancel"
            onClick={() => {
              setBuilderOpen(false);
              setBuilderMessage(null);
            }}
          >
            {t("fxauto.builderCancel")}
          </button>
        </form>
      ) : null}

      {projectId === null ? null : (
        <>
          <h3 data-testid="auto-approvals-title">
            {t("fxauto.approvalsTitle")}
          </h3>
          {data.approvals.length === 0 ? (
            <p data-testid="auto-approvals-empty">
              {t("fxauto.approvalsEmpty")}
            </p>
          ) : (
            <div data-testid="auto-approvals">
              {data.approvals.map((approval) => (
                <section
                  key={approval.approval_id}
                  data-testid={`auto-approval-${approval.approval_id}`}
                  className="fxauto-card"
                >
                  <h4>{approval.rule_name}</h4>
                  <p>
                    {doText(approval.action)} ·{" "}
                    {approval.state === "pending"
                      ? t("fxauto.approvalPending")
                      : approval.state === "approved"
                        ? t("fxauto.approvalApproved")
                        : t("fxauto.approvalRejected")}
                  </p>
                  {approval.state === "pending" ? (
                    <>
                      <button
                        type="button"
                        data-testid={`auto-approval-${approval.approval_id}-approve`}
                        onClick={() => {
                          void decide(approval, true);
                        }}
                      >
                        {t("fxauto.approve")}
                      </button>
                      <button
                        type="button"
                        data-testid={`auto-approval-${approval.approval_id}-reject`}
                        onClick={() => {
                          void decide(approval, false);
                        }}
                      >
                        {t("fxauto.reject")}
                      </button>
                    </>
                  ) : null}
                </section>
              ))}
            </div>
          )}

          <h3 data-testid="auto-history-title">
            {t("fxauto.historyTitle")}
          </h3>
          {data.runs.length === 0 ? (
            <p data-testid="auto-history-empty">
              {t("fxauto.historyEmpty")}
            </p>
          ) : (
            <div data-testid="auto-history">
              {data.runs.map((row) => (
                <div
                  key={row.run_id}
                  data-testid={`auto-run-${row.run_id}`}
                  className="fxauto-row"
                >
                  <span>
                    {row.time === null
                      ? t("fxauto.noNextRun")
                      : formatScreenTime(row.time)}
                  </span>{" "}
                  <span>{row.rule}</span> <span>{row.state}</span>{" "}
                  <span>{resultText(row.result)}</span>
                </div>
              ))}
            </div>
          )}

          <h3 data-testid="auto-checkpoints-title">
            {t("fxauto.checkpointsTitle")}
          </h3>
          {data.latest === null ? (
            <p data-testid="auto-checkpoints-empty">
              {t("fxauto.checkpointsEmpty")}
            </p>
          ) : (
            <p data-testid="auto-resume-available">
              {t("fxauto.resumeAvailable", { id: data.latest.checkpoint_id })}
            </p>
          )}
          {data.checkpoints.length === 0 ? null : (
            <div data-testid="auto-checkpoints">
              {data.checkpoints.map((checkpoint) => (
                <div
                  key={checkpoint.checkpoint_id}
                  data-testid={`auto-checkpoint-${checkpoint.checkpoint_id}`}
                  className="fxauto-row"
                >
                  <span>
                    {checkpoint.time === ""
                      ? checkpoint.checkpoint_id
                      : formatScreenTime(checkpoint.time)}
                  </span>{" "}
                  <span>{checkpoint.rule}</span>{" "}
                  <span>
                    {t("fxauto.checkpointDigest")}: {checkpoint.digest}
                  </span>{" "}
                  <button
                    type="button"
                    data-testid={`auto-checkpoint-${checkpoint.checkpoint_id}-resume`}
                    onClick={() => {
                      void resume(checkpoint);
                    }}
                  >
                    {t("fxauto.resume")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
