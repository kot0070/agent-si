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
import {HttpApiClient} from "../../api/client";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { ENDPOINTS } from "../../api/endpoints";
import type { TaskRecord } from "../../api/iface";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { TaskComposer } from "../TaskComposer";
import { readTaskRunMarker, startTaskRun } from "../startTaskRun";
import { startHierarchyRun } from "../hierarchyRun";
import type { StoredGateRefs } from "../hierarchyRun";
import { TeamModelQuickFix } from "../TeamModelQuickFix";

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

const PASS_REFS: StoredGateRefs = {
  packageId: "pkg-1",
  gate: "PASS",
  audit: "PASS",
  evidenceRefs: ["gate-1", "audit-1"],
};

interface SeenCall {
  url: string;
  method: string;
  body: unknown;
}

function stubTaskFetch(task: TaskRecord): {
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

describe("task composer", () => {
  it("posts through the client entry to the projects tasks route", async () => {
    const { seen, release } = stubTaskFetch({
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
    fireEvent.change(screen.getByTestId("composer-title"), {
      target: { value: "task one" },
    });
    fireEvent.change(screen.getByTestId("composer-scope"), {
      target: { value: "s-1, s-2" },
    });
    fireEvent.click(screen.getByTestId("composer-create"));
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
    expect(screen.getByTestId("composer-task-id").textContent).toBe("t-7");
    expect(screen.getByTestId("composer-status").textContent).toBe(
      t("tasks.status.queued"),
    );
  });

  it("a late status load never overwrites a user-edited value", async () => {
    const { release } = stubTaskFetch({
      task_id: "t-9",
      project_id: "p-1",
      title: "loaded title",
      status: "QUEUED",
      created_at: "t-0",
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" initialTaskId="t-9" />
      </ApiClientProvider>,
    );
    const title = screen.getByTestId("composer-title") as HTMLInputElement;
    fireEvent.change(title, { target: { value: "user edit" } });
    await act(async () => {
      release();
    });
    expect(
      (screen.getByTestId("composer-title") as HTMLInputElement).value,
    ).toBe("user edit");
  });

  it("applies the loaded title when the user never edited it", async () => {
    const { release } = stubTaskFetch({
      task_id: "t-9",
      project_id: "p-1",
      title: "loaded title",
      status: "QUEUED",
      created_at: "t-0",
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" initialTaskId="t-9" />
      </ApiClientProvider>,
    );
    await act(async () => {
      release();
    });
    expect(
      (screen.getByTestId("composer-title") as HTMLInputElement).value,
    ).toBe("loaded title");
  });
});

describe("task run starter", () => {
  it("hits the stream route and records the session marker", async () => {
    const client = new FakeApiClient({ chatDeltas: ["ta", "sk"] });
    const texts: string[] = [];
    const handle = startTaskRun(client, {
      projectId: "p-1",
      promptRef: "pr-1",
      streamId: "s-run-1",
      taskId: "t-1",
      onText: (text) => {
        texts.push(text);
      },
    });
    await handle.done;
    expect(texts.join("")).toBe("task");
    expect(handle.marker).toMatchObject({
      stream_id: "s-run-1",
      project_id: "p-1",
      task_id: "t-1",
    });
    expect(readTaskRunMarker("s-run-1")).toMatchObject({
      stream_id: "s-run-1",
      project_id: "p-1",
      task_id: "t-1",
    });
  });

  it("reaches the chat stream endpoint through the http client", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
      return new Response(
        'data: {"stream_id":"s-2","delta":"hi","done":true}\n',
        {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        },
      );
    });
    const client = new HttpApiClient();
    const texts: string[] = [];
    const handle = startTaskRun(client, {
      projectId: "p-1",
      promptRef: "pr-1",
      streamId: "s-2",
      onText: (text) => {
        texts.push(text);
      },
    });
    await handle.done;
    expect(seen).toContain(ENDPOINTS.chatStream);
    expect(texts.join("")).toBe("hi");
  });

  it("rejects an empty prompt ref without touching the stream", () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
      throw new Error(`unexpected fetch to ${String(url)}`);
    });
    const client = new HttpApiClient();
    let error: unknown = null;
    try {
      startTaskRun(client, {
        projectId: "p-1",
        promptRef: "",
        streamId: "s-bad",
        onText: () => undefined,
      });
    } catch (thrown) {
      error = thrown;
    }
    expect(error).toMatchObject({ code: "CONTEXT_WRONG_CONTRACT_VERSION" });
    expect(readTaskRunMarker("s-bad")).toBeNull();
    expect(seen).toEqual([]);
  });
});

describe("hierarchy run helper", () => {
  it("refuses without a stored gate PASS", async () => {
    const client = new FakeApiClient({});
    await expect(
      startHierarchyRun(client, {
        projectId: "p-1",
        title: "child",
        scope: ["s-1"],
        refs: { ...PASS_REFS, gate: "BLOCKED" },
      }),
    ).rejects.toMatchObject({ code: "GATE_NOT_PASSED" });
  });

  it("refuses without a stored audit PASS", async () => {
    const client = new FakeApiClient({});
    await expect(
      startHierarchyRun(client, {
        projectId: "p-1",
        title: "child",
        scope: ["s-1"],
        refs: { ...PASS_REFS, audit: "BLOCKED" },
      }),
    ).rejects.toMatchObject({ code: "AUDIT_INDEPENDENCE_REJECTED" });
  });

  it("refuses without stored evidence refs", async () => {
    const client = new FakeApiClient({});
    await expect(
      startHierarchyRun(client, {
        projectId: "p-1",
        title: "child",
        scope: ["s-1"],
        refs: { ...PASS_REFS, evidenceRefs: [] },
      }),
    ).rejects.toMatchObject({ code: "INVALID_HIERARCHY_CHAIN" });
  });

  it("starts the task over stored gate plus audit PASS refs", async () => {
    const client = new FakeApiClient({});
    const task = await startHierarchyRun(client, {
      projectId: "p-1",
      title: "child",
      scope: ["s-1"],
      refs: PASS_REFS,
    });
    expect(task.title).toBe("child");
    expect(task.status).toBe("QUEUED");
  });
});

describe("team model quick fix", () => {
  it("shows the stored binding and applies it on accept", async () => {
    const client = new FakeApiClient({});
    const applied: Array<{ providerId: string; model: string }> = [];
    let dismissed = 0;
    render(
      <ApiClientProvider client={client}>
        <TeamModelQuickFix
          projectId="p-1"
          providerId="prov-1"
          model="model-1"
          onApply={(binding) => {
            applied.push(binding);
          }}
          onDismiss={() => {
            dismissed += 1;
          }}
        />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("team-quickfix")).toBeTruthy();
    expect(screen.getByTestId("quickfix-provider").textContent).toBe("prov-1");
    expect(screen.getByTestId("quickfix-model").textContent).toBe("model-1");
    expect(screen.getByTestId("quickfix-mode").textContent).toBe(
      t("settings.roleProfile.modes.pinned"),
    );
    fireEvent.click(screen.getByTestId("quickfix-accept"));
    expect(applied).toEqual([{ providerId: "prov-1", model: "model-1" }]);
    fireEvent.click(screen.getByTestId("quickfix-dismiss"));
    expect(dismissed).toBe(1);
  });

  it("resolves every used key in both frozen locales", () => {
    setLocale("en");
    const english = [
      t("tasks.creator.title"),
      t("tasks.creator.create"),
      t("tasks.list.empty"),
      t("tasks.status.queued"),
      t("agents.row.scope"),
      t("settings.roleProfile.title"),
    ];
    setLocale("uk");
    const ukrainian = [
      t("tasks.creator.title"),
      t("tasks.creator.create"),
      t("tasks.list.empty"),
      t("tasks.status.queued"),
      t("agents.row.scope"),
      t("settings.roleProfile.title"),
    ];
    for (let index = 0; index < english.length; index += 1) {
      expect((english[index] ?? "").length).toBeGreaterThan(0);
      expect((ukrainian[index] ?? "").length).toBeGreaterThan(0);
      expect(ukrainian[index]).not.toBe(english[index]);
    }
  });
});
