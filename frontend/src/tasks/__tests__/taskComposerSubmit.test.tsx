/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { ENDPOINTS } from "../../api/endpoints";
import type { TaskRecord } from "../../api/iface";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { TASK_SUBMIT_TIMEOUT_MS, TaskComposer } from "../TaskComposer";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

interface SeenCall {
  url: string;
  method: string;
  body: unknown;
}

function stubGatedTaskFetch(task: TaskRecord): {
  seen: SeenCall[];
  release: () => void;
} {
  const seen: SeenCall[] = [];
  let release!: () => void;
  const gate = new Promise<Response>((resolve) => {
    release = () =>
      resolve(
        new Response(JSON.stringify({ task }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
  });
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string; body?: string }) => {
      seen.push({
        url: String(url),
        method: init?.method ?? "GET",
        body:
          init?.body === undefined
            ? undefined
            : (JSON.parse(init.body) as unknown),
      });
      return gate;
    },
  );
  return { seen, release: () => release() };
}

function fillTitle(value: string): void {
  fireEvent.change(screen.getByTestId("composer-title"), {
    target: { value },
  });
}

function cancelButton(): HTMLButtonElement {
  return screen.getByTestId("composer-cancel") as HTMLButtonElement;
}

function createButton(): HTMLButtonElement {
  return screen.getByTestId("composer-create") as HTMLButtonElement;
}

describe("task composer submit timeout and cancel", () => {
  it("posts through the client entry to the ENDPOINTS.tasks route", async () => {
    const { seen, release } = stubGatedTaskFetch({
      task_id: "t-7",
      project_id: "p-1",
      title: "task one",
      status: "QUEUED",
      created_at: "t-0",
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(cancelButton().disabled).toBe(true);
    fillTitle("task one");
    fireEvent.change(screen.getByTestId("composer-scope"), {
      target: { value: "s-1, s-2" },
    });
    fireEvent.click(createButton());
    expect(cancelButton().disabled).toBe(false);
    await act(async () => {
      release();
    });
    expect(await screen.findByTestId("composer-result")).toBeTruthy();
    const posts = seen.filter((call) => call.method === "POST");
    expect(posts.length).toBe(1);
    expect(posts[0]?.url).toContain(ENDPOINTS.tasks);
    expect(posts[0]?.body).toEqual({
      title: "task one",
      scope: ["s-1", "s-2"],
    });
  });

  it("shows a blocking error when the submit exceeds the bounded timeout", async () => {
    vi.useFakeTimers();
    const { release } = stubGatedTaskFetch({
      task_id: "t-8",
      project_id: "p-1",
      title: "slow task",
      status: "QUEUED",
      created_at: "t-0",
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" />
      </ApiClientProvider>,
    );
    fillTitle("slow task");
    fireEvent.click(createButton());
    expect(createButton().disabled).toBe(true);
    expect(cancelButton().disabled).toBe(false);
    await act(async () => {
      vi.advanceTimersByTime(TASK_SUBMIT_TIMEOUT_MS);
    });
    expect(screen.getByTestId("kit-error-panel")).toBeTruthy();
    expect(createButton().disabled).toBe(false);
    await act(async () => {
      release();
    });
    expect(screen.queryByTestId("composer-result")).toBeNull();
    expect(createButton().disabled).toBe(false);
  });

  it("cancel aborts a pending submit to idle with no result", async () => {
    const { release } = stubGatedTaskFetch({
      task_id: "t-9",
      project_id: "p-1",
      title: "cancelled task",
      status: "QUEUED",
      created_at: "t-0",
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" />
      </ApiClientProvider>,
    );
    fillTitle("cancelled task");
    fireEvent.click(createButton());
    expect(cancelButton().disabled).toBe(false);
    fireEvent.click(cancelButton());
    expect(createButton().disabled).toBe(false);
    expect(screen.queryByTestId("composer-result")).toBeNull();
    await act(async () => {
      release();
    });
    expect(screen.queryByTestId("composer-result")).toBeNull();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(createButton().disabled).toBe(false);
  });
});
