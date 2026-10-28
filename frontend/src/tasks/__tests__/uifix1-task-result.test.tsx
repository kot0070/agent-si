/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import type { TaskRecord } from "../../api/iface";
import {
  formatDate,
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { LocaleProvider } from "../../locale/index";
import type { SupportedLocale } from "../../locale/index";
import { ProjectView } from "../../projects/ProjectView";
import { TaskComposer } from "../TaskComposer";

interface TaskStore {
  tasks: TaskRecord[];
  seen: string[];
}

function seedTask(overrides: Partial<TaskRecord> = {}): TaskRecord {
  return {
    task_id: "t-1",
    project_id: "p-1",
    title: "seed one",
    status: "QUEUED",
    created_at: "2026-01-05T00:00:00.000Z",
    ...overrides,
  };
}

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function stubTaskBoundary(store: TaskStore): void {
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string; body?: string }) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      store.seen.push(`${method} ${path}`);
      if (path === "/api/v1/projects/p-1" && method === "GET") {
        return jsonBody({
          project: {
            project_id: "p-1",
            name: "n-1",
            created_at: "2026-01-01T00:00:00.000Z",
          },
        });
      }
      if (path === "/api/v1/tasks?project_id=p-1" && method === "GET") {
        return jsonBody({ tasks: store.tasks });
      }
      if (path === "/api/v1/tasks?project_id=p-1" && method === "POST") {
        const body = JSON.parse(init?.body ?? "{}") as {
          title?: unknown;
          scope?: unknown;
        };
        const task: TaskRecord = {
          task_id: `t-${store.tasks.length + 1}`,
          project_id: "p-1",
          title: String(body.title ?? ""),
          status: "CREATED",
          created_at: "2026-03-04T05:06:07.000Z",
        };
        store.tasks.push(task);
        return jsonBody({ task });
      }
      if (path === "/api/v1/runs/ledger?project_id=p-1" && method === "GET") {
        return jsonBody({ rows: [] });
      }
      if (path === "/api/v1/budget?project_id=p-1" && method === "GET") {
        return jsonBody({
          state: {
            project_id: "p-1",
            hard_limit: 100,
            spent: 10,
            reserved: 5,
            currency: "u-1",
          },
        });
      }
      if (path === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
  );
}

function renderComposer(locale: SupportedLocale): void {
  setLocale(locale);
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <LocaleProvider initialLocale={locale}>
        <TaskComposer projectId="p-1" />
      </LocaleProvider>
    </ApiClientProvider>,
  );
}

function renderTasks(locale: SupportedLocale): void {
  setLocale(locale);
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <LocaleProvider initialLocale={locale}>
        <ProjectView projectId="p-1" view="tasks" />
        <TaskComposer projectId="p-1" />
      </LocaleProvider>
    </ApiClientProvider>,
  );
}

function taskListCalls(store: TaskStore): number {
  return store.seen.filter(
    (line) => line === "GET /api/v1/tasks?project_id=p-1",
  ).length;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("uifix1 task result", () => {
  it("shows the typed title with a localized status and keeps the id out of view", async () => {
    const store: TaskStore = { tasks: [seedTask()], seen: [] };
    stubTaskBoundary(store);
    renderComposer("en");
    fireEvent.change(screen.getByTestId("composer-title"), {
      target: { value: "typed title nine" },
    });
    fireEvent.click(screen.getByTestId("composer-create"));
    const result = await screen.findByTestId("composer-result");
    expect(screen.getByTestId("composer-title-result").textContent).toBe(
      "typed title nine",
    );
    expect(screen.getByTestId("composer-status").textContent).toBe(
      t("tasks.status.queued"),
    );
    expect(screen.getByTestId("composer-status").textContent).not.toBe(
      "CREATED",
    );
    expect(screen.getByTestId("composer-status").textContent).not.toContain(
      "t-2",
    );
    const id = screen.getByTestId("composer-task-id");
    expect(id.textContent).toBe("t-2");
    expect(id.hasAttribute("hidden")).toBe(true);
    expect(result.textContent).not.toContain("CREATED");
  });

  it("renders a different localized status in uk", async () => {
    const store: TaskStore = { tasks: [seedTask()], seen: [] };
    stubTaskBoundary(store);
    renderComposer("uk");
    fireEvent.change(screen.getByTestId("composer-title"), {
      target: { value: "typed title nine" },
    });
    fireEvent.click(screen.getByTestId("composer-create"));
    await screen.findByTestId("composer-result");
    const status = screen.getByTestId("composer-status").textContent;
    expect(status).toBe(t("tasks.status.queued"));
    setLocale("en");
    expect(t("tasks.status.queued")).not.toBe(status);
  });

  it("refetches the tasks list after a create and shows the new row without remount", async () => {
    const store: TaskStore = { tasks: [seedTask()], seen: [] };
    stubTaskBoundary(store);
    renderTasks("en");
    await screen.findByTestId("task-row-t-1");
    const before = taskListCalls(store);
    expect(before).toBeGreaterThan(0);
    fireEvent.change(screen.getByTestId("composer-title"), {
      target: { value: "fresh nine" },
    });
    fireEvent.click(screen.getByTestId("composer-create"));
    const row = await screen.findByTestId("task-row-t-2");
    expect(row.textContent).toContain("fresh nine");
    expect(taskListCalls(store)).toBeGreaterThan(before);
  });

  it("formats an ISO stamp instead of printing it raw", async () => {
    const iso = "2026-01-05T00:00:00.000Z";
    const store: TaskStore = { tasks: [seedTask()], seen: [] };
    stubTaskBoundary(store);
    setLocale("en");
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocaleProvider initialLocale="en">
          <ProjectView projectId="p-1" view="tasks" />
        </LocaleProvider>
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("task-row-t-1");
    expect(row.textContent).toContain(formatDate(new Date(iso), "en"));
    expect(row.textContent).not.toContain(iso);
  });

  it("shows an unknown status as is instead of blank", async () => {
    const store: TaskStore = {
      tasks: [seedTask({ status: "WOBBLE_X", created_at: "WOBBLE_NOT_A_DATE" })],
      seen: [],
    };
    stubTaskBoundary(store);
    setLocale("en");
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocaleProvider initialLocale="en">
          <ProjectView projectId="p-1" view="tasks" />
        </LocaleProvider>
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("task-row-t-1");
    expect(row.textContent).toContain("WOBBLE_X");
    expect(row.textContent).toContain("WOBBLE_NOT_A_DATE");
  });
});
