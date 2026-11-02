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
  readTeamMode,
  saveBudgetLimits,
  saveParallelParts,
  saveStepLimits,
  saveTeamMode,
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
  const [teamText, setTeamText] = useState<"on" | "off">("on");
  const [budgetText, setBudgetText] = useState<string | null>(null);
  const [capsText, setCapsText] = useState("");
  const [spendingLines, setSpendingLines] = useState<ReadonlyArray<string>>(
    [],
  );
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parallelSaving, setParallelSaving] = useState(false);
  const [teamSaving, setTeamSaving] = useState(false);
  const [capsSaving, setCapsSaving] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
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
        let team: "on" | "off" = "on";
        try {
          const storedTeam = await readTeamMode(props.projectId);
          team = storedTeam.team;
        } catch {
          team = "on";
        }
        if (!alive) {
          return;
        }
        setTaskText(String(limits.task_max_steps));
        setChatText(String(limits.chat_max_steps));
        setParallelText(String(parallel));
        setTeamText(team);
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
    // FXCLASS CA-6: a blank limit input shows a field message, sends
    // nothing, and never falls back to a generic error.
    const taskRaw = taskText.trim();
    const chatRaw = chatText.trim();
    if (taskRaw === "" || chatRaw === "") {
      setFieldError("settings.project.limitsBlank");
      return;
    }
    const task = Number(taskRaw);
    const chat = Number(chatRaw);
    if (!Number.isInteger(task) || !Number.isInteger(chat) || task < 1 || chat < 1) {
      setFieldError("settings.project.limitsBlank");
      return;
    }
    setFieldError(null);
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
    const raw = parallelText.trim();
    if (raw === "") {
      setFieldError("settings.project.limitsBlank");
      return;
    }
    const parallel = Number(raw);
    if (
      !Number.isInteger(parallel) ||
      parallel < 1 ||
      parallel > 4
    ) {
      setFieldError("settings.project.limitsBlank");
      return;
    }
    setFieldError(null);
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

  async function onSaveTeam(): Promise<void> {
    if (teamText !== "on" && teamText !== "off") {
      setErrorKey("errors.generic");
      return;
    }
    setTeamSaving(true);
    try {
      const saved = await saveTeamMode(props.projectId, teamText);
      if (saved.project_id !== props.projectId) {
        setErrorKey("errors.generic");
        return;
      }
      setTeamText(saved.team);
      setErrorKey(null);
      setNonce((value) => value + 1);
    } catch (error) {
      setErrorKey(errorKeyOf(error));
    } finally {
      setTeamSaving(false);
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
      {fieldError !== null ? (
        <p data-testid="project-limits-field-error">{t(fieldError)}</p>
      ) : null}
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
        {t("chat.composer.send")}
      </button>
      <label htmlFor="project-limits-team">{t("settings.project.team")}</label>
      <select
        id="project-limits-team"
        data-testid="project-limits-team"
        value={teamText}
        onChange={(event: { target: { value: string } }) => {
          const next = event.target.value;
          if (next === "on" || next === "off") {
            setTeamText(next);
          }
        }}
      >
        <option value="on">{t("settings.project.teamOn")}</option>
        <option value="off">{t("settings.project.teamOff")}</option>
      </select>
      <button
        type="button"
        data-testid="project-limits-team-save"
        disabled={teamSaving}
        onClick={() => {
          void onSaveTeam();
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
        {t("chat.composer.send")}
      </button>
    </section>
  );
}
