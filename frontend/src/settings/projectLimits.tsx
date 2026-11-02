// kit BUILD_PLAN line 488: "Max agent steps is a project setting, with a
// separate value for chat; the real guards are the budget and Stop all
// (a step limit never replaces them)".

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { t } from "../locale/index";
import {
  readBudgetLine,
  readParallelParts,
  readStepLimits,
  saveBudgetLimits,
  saveParallelParts,
  saveStepLimits,
} from "./projectLimitsApi";

export interface ProjectLimitsSectionProps {
  projectId: string;
}

function errorKeyOf(error: unknown): string {
  if (error instanceof ApiError) {
    return apiErrorLocaleKey(error.code);
  }
  return "errors.generic";
}

export function ProjectLimitsSection(
  props: ProjectLimitsSectionProps,
): ReactElement {
  const [taskText, setTaskText] = useState("");
  const [chatText, setChatText] = useState("");
  const [parallelText, setParallelText] = useState("1");
  const [budgetText, setBudgetText] = useState<string | null>(null);
  const [capsText, setCapsText] = useState("");
  const [spendingLines, setSpendingLines] = useState<ReadonlyArray<string>>(
    [],
  );
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parallelSaving, setParallelSaving] = useState(false);
  const [capsSaving, setCapsSaving] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  function parseCapsText(raw: string): Record<string, string> | null {
    const trimmed = raw.trim();
    if (trimmed === "") {
      return {};
    }
    const out: Record<string, string> = {};
    for (const part of trimmed.split(",")) {
      const cell = part.trim();
      const sep = cell.indexOf(":");
      if (sep < 0) {
        return null;
      }
      const provider = cell.slice(0, sep).trim();
      const amount = cell.slice(sep + 1).trim();
      if (provider === "" || !/^\d+(\.\d+)?$/.test(amount)) {
        return null;
      }
      out[provider] = amount;
    }
    return out;
  }

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const [limits, budget] = await Promise.all([
          readStepLimits(props.projectId),
          readBudgetLine(props.projectId),
        ]);
        let parallel = 1;
        try {
          const stored = await readParallelParts(props.projectId);
          parallel = stored.max_parallel_parts;
        } catch {
          parallel = 1;
        }
        if (!alive) {
          return;
        }
        setTaskText(String(limits.task_max_steps));
        setChatText(String(limits.chat_max_steps));
        setParallelText(String(parallel));
        setBudgetText(
          `${budget.budget.spent} / ${budget.budget.hard_limit} ${budget.budget.currency}`,
        );
        const caps = budget.budget.provider_spend_caps ?? {};
        setCapsText(
          Object.entries(caps)
            .map(([provider, amount]) => `${provider}:${amount}`)
            .join(", "),
        );
        const spending = budget.budget.provider_spending ?? {};
        setSpendingLines(
          Object.entries(spending).map(([provider, row]) =>
            row.cap === null
              ? `${provider}: ${row.spent} (no cap) ${budget.budget.currency}`
              : `${provider}: ${row.spent} / ${row.cap} ${budget.budget.currency}`,
          ),
        );
        setErrorKey(null);
        setLoaded(true);
      } catch (error) {
        if (!alive) {
          return;
        }
        setErrorKey(errorKeyOf(error));
        setLoaded(true);
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [props.projectId, nonce]);

  async function onSave(): Promise<void> {
    const task = Number(taskText);
    const chat = Number(chatText);
    if (!Number.isInteger(task) || !Number.isInteger(chat)) {
      setErrorKey("errors.generic");
      return;
    }
    setSaving(true);
    try {
      const saved = await saveStepLimits(props.projectId, task, chat);
      if (saved.project_id !== props.projectId) {
        setErrorKey("errors.generic");
        return;
      }
      setTaskText(String(saved.task_max_steps));
      setChatText(String(saved.chat_max_steps));
      setErrorKey(null);
      setNonce((value) => value + 1);
    } catch (error) {
      setErrorKey(errorKeyOf(error));
    } finally {
      setSaving(false);
    }
  }

  async function onSaveCaps(): Promise<void> {
    const caps = parseCapsText(capsText);
    if (caps === null) {
      setErrorKey("errors.generic");
      return;
    }
    setCapsSaving(true);
    try {
      const saved = await saveBudgetLimits(props.projectId, caps);
      if (saved.project_id !== props.projectId) {
        setErrorKey("errors.generic");
        return;
      }
      setErrorKey(null);
      setNonce((value) => value + 1);
    } catch (error) {
      setErrorKey(errorKeyOf(error));
    } finally {
      setCapsSaving(false);
    }
  }

  async function onSaveParallel(): Promise<void> {
    const parallel = Number(parallelText);
    if (
      !Number.isInteger(parallel) ||
      parallel < 1 ||
      parallel > 4
    ) {
      setErrorKey("errors.generic");
      return;
    }
    setParallelSaving(true);
    try {
      const saved = await saveParallelParts(props.projectId, parallel);
      if (saved.project_id !== props.projectId) {
        setErrorKey("errors.generic");
        return;
      }
      setParallelText(String(saved.max_parallel_parts));
      setErrorKey(null);
      setNonce((value) => value + 1);
    } catch (error) {
      setErrorKey(errorKeyOf(error));
    } finally {
      setParallelSaving(false);
    }
  }

  if (!loaded) {
    return (
      <section data-testid="project-limits-section">
        <p>{t("ui.loading.more")}</p>
      </section>
    );
  }

  return (
    <section data-testid="project-limits-section">
      <h2>{t("settings.project.title")}</h2>
      <p>{t("settings.project.purpose")}</p>
      <p>{t("settings.project.needItNow")}</p>
      {errorKey !== null ? (
        <div data-testid="project-limits-error">
          <span>{t(errorKey)}</span>
          <button
            type="button"
            data-testid="project-limits-retry"
            onClick={() => {
              setLoaded(false);
              setErrorKey(null);
              setNonce((value) => value + 1);
            }}
          >
            {t("ui.error.retry")}
          </button>
        </div>
      ) : null}
      <label htmlFor="project-limits-task">{t("tasks.list.title")}</label>
      <input
        id="project-limits-task"
        data-testid="project-limits-task"
        type="number"
        value={taskText}
        onChange={(event: { target: { value: string } }) => {
          setTaskText(event.target.value);
        }}
      />
      <label htmlFor="project-limits-chat">{t("shell.sidebar.chat")}</label>
      <input
        id="project-limits-chat"
        data-testid="project-limits-chat"
        type="number"
        value={chatText}
        onChange={(event: { target: { value: string } }) => {
          setChatText(event.target.value);
        }}
      />
      <button
        type="button"
        data-testid="project-limits-save"
        disabled={saving}
        onClick={() => {
          void onSave();
        }}
      >
        {t("settings.project.save")}
      </button>
      <label htmlFor="project-limits-parallel">
        {t("settings.project.parallel")}
      </label>
      <input
        id="project-limits-parallel"
        data-testid="project-limits-parallel"
        type="number"
        min={1}
        max={4}
        value={parallelText}
        onChange={(event: { target: { value: string } }) => {
          setParallelText(event.target.value);
        }}
      />
      <button
        type="button"
        data-testid="project-limits-parallel-save"
        disabled={parallelSaving}
        onClick={() => {
          void onSaveParallel();
        }}
      >
        {t("settings.project.save")}
      </button>
      {budgetText !== null ? (
        <div data-testid="project-limits-budget">
          <span>{t("projects.cost.title")}</span>
          <span>{budgetText}</span>
        </div>
      ) : null}
      <div data-testid="project-limits-spending">
        {spendingLines.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </div>
      <label htmlFor="project-limits-caps">{t("projects.cost.title")}</label>
      <input
        id="project-limits-caps"
        data-testid="project-limits-caps"
        type="text"
        value={capsText}
        onChange={(event: { target: { value: string } }) => {
          setCapsText(event.target.value);
        }}
      />
      <button
        type="button"
        data-testid="project-limits-caps-save"
        disabled={capsSaving}
        onClick={() => {
          void onSaveCaps();
        }}
      >
        {t("settings.project.save")}
      </button>
    </section>
  );
}
