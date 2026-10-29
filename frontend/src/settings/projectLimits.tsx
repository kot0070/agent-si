// kit BUILD_PLAN line 488: "Max agent steps is a project setting, with a
// separate value for chat; the real guards are the budget and Stop all
// (a step limit never replaces them)".

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { t } from "../locale/index";
import {
  readBudgetLine,
  readStepLimits,
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
  const [budgetText, setBudgetText] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const [limits, budget] = await Promise.all([
          readStepLimits(props.projectId),
          readBudgetLine(props.projectId),
        ]);
        if (!alive) {
          return;
        }
        setTaskText(String(limits.task_max_steps));
        setChatText(String(limits.chat_max_steps));
        setBudgetText(
          `${budget.budget.spent} / ${budget.budget.hard_limit} ${budget.budget.currency}`,
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
        {t("chat.composer.send")}
      </button>
      {budgetText !== null ? (
        <div data-testid="project-limits-budget">
          <span>{t("projects.cost.title")}</span>
          <span>{budgetText}</span>
        </div>
      ) : null}
    </section>
  );
}
