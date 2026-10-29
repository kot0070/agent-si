// Lane A ApiClient implementations: HttpApiClient over fetch and
// FakeApiClient with fixture rows. HttpApiClient delegates every typed
// call to the api area modules; FakeApiClient validates with the same
// zod schemas the real path enforces.

import type {
  ApiClient,
  BudgetState,
  ChatChunk,
  ChatOpen,
  ChatStream,
  LedgerRow,
  PackageReport,
  PartRow,
  ProjectCreate,
  ProjectPatch,
  ProjectRecord,
  RoutingWhy,
  TaskCreate,
  TaskRecord,
} from "./iface";
import { ENDPOINTS } from "./endpoints";
import {
  ApiError,
  apiErrorFromCode,
  parseOrThrow,
  requestResponse,
} from "./errors";
import { listAgentsLiveRows, parseAgentsLive } from "./agentsApi";
import { PartRowSchema } from "./agentsApi";
import {
  ChatCancelSchema,
  ChatOpenSchema,
  ChatStreamEventSchema,
  ProjectCreateSchema,
  ProjectPatchSchema,
  TaskCreateSchema,
  cancelChatStreamRequest,
  createProjectRecord,
  createTaskRecord,
  deleteProjectRecord,
  listProjectRecords,
  listTaskRecords,
  readBudgetState,
  readLedgerRows,
  readPackageReport,
  readProjectRecord,
  readRoutingWhyDetail,
  readTaskRecord,
  updateProjectRecord,
} from "./projectsApi";

export interface HttpClientOptions {
  actor?: string;
}

export class HttpApiClient implements ApiClient {
  private readonly actor: string | undefined;

  constructor(options: HttpClientOptions = {}) {
    this.actor = options.actor;
  }

  listAgentsLive(): Promise<PartRow[]> {
    return listAgentsLiveRows();
  }

  readLedger(project_id: string): Promise<LedgerRow[]> {
    return readLedgerRows(project_id);
  }

  readNextPackageNudge(package_id: string): Promise<PackageReport> {
    return readPackageReport(package_id);
  }

  readRoutingWhy(decision_id: string): Promise<RoutingWhy> {
    return readRoutingWhyDetail(decision_id);
  }

  listProjects(): Promise<ProjectRecord[]> {
    return listProjectRecords();
  }

  readProject(project_id: string): Promise<ProjectRecord> {
    return readProjectRecord(project_id);
  }

  createProject(body: ProjectCreate): Promise<ProjectRecord> {
    return createProjectRecord(body);
  }

  updateProject(
    project_id: string,
    body: ProjectPatch,
  ): Promise<ProjectRecord> {
    return updateProjectRecord(project_id, body);
  }

  deleteProject(project_id: string): Promise<void> {
    return deleteProjectRecord(project_id);
  }

  listTasks(project_id: string): Promise<TaskRecord[]> {
    return listTaskRecords(project_id);
  }

  readTask(task_id: string): Promise<TaskRecord> {
    return readTaskRecord(task_id);
  }

  createTask(project_id: string, body: TaskCreate): Promise<TaskRecord> {
    return createTaskRecord(project_id, body);
  }

  openChatStream(body: ChatOpen): ChatStream {
    let request: ChatOpen;
    try {
      request = parseOrThrow(ChatOpenSchema, body, 400);
    } catch {
      throw new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400);
    }
    const requestedId = request.stream_id;
    const actor = this.actor;
    const url = ENDPOINTS.chatStream;
    let effectiveId = requestedId;
    let serverIdSeen = false;
    const adoptServerId = (value: unknown): void => {
      if (!serverIdSeen && typeof value === "string" && value.length > 0) {
        effectiveId = value;
        serverIdSeen = true;
      }
    };
    function terminal(): ChatChunk {
      return { stream_id: effectiveId, delta: "", done: true };
    }
    let finished = false;
    function* handleLine(line: string, status: number): Generator<ChatChunk, void, void> {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) {
        return;
      }
      const payload = trimmed.slice("data:".length).trim();
      if (payload === "" || payload === "[DONE]") {
        return;
      }
      let event: unknown;
      try {
        event = JSON.parse(payload) as unknown;
      } catch {
        return;
      }
      if (typeof event !== "object" || event === null) {
        return;
      }
      const record = event as Record<string, unknown>;
      if (typeof record["type"] === "string") {
        const parsed = ChatStreamEventSchema.safeParse(record);
        if (!parsed.success) {
          return;
        }
        const wire = parsed.data;
        switch (wire.type) {
          case "start": {
            adoptServerId(wire.stream_id);
            break;
          }
          case "delta": {
            if (typeof wire.text === "string" && wire.text !== "") {
              yield {
                stream_id: effectiveId,
                delta: wire.text,
                done: false,
              };
            }
            break;
          }
          case "done":
          case "cancelled": {
            finished = true;
            yield terminal();
            return;
          }
          case "error": {
            throw apiErrorFromCode(wire.code, status);
          }
          case "approval": {
            throw new ApiError("APPROVAL_REQUIRED", status);
          }
          default: {
            break;
          }
        }
      } else if ("delta" in record || "done" in record) {
        const delta = typeof record["delta"] === "string" ? record["delta"] : "";
        const done = record["done"] === true;
        yield { stream_id: effectiveId, delta, done };
        if (done) {
          finished = true;
          return;
        }
      }
    }
    async function* chunks(): AsyncGenerator<ChatChunk, void, void> {
      let response: Response;
      try {
        response = await requestResponse(
          url,
          {
            method: "POST",
            kind: "chat",
            body: { project: request.project_id, message: request.prompt_ref },
            actor,
          },
        );
      } catch (error) {
        if (
          error instanceof ApiError &&
          (error.code === "CONTEXT_MISSING" || error.status === 404)
        ) {
          throw new ApiError("NO_PROVIDER_BOUND", error.status);
        }
        throw error;
      }
      adoptServerId(response.headers.get("x-stream-id"));
      const status = response.status;
      finished = false;
      const rawBody = response.body;
      if (
        rawBody === undefined ||
        rawBody === null ||
        typeof TextDecoder === "undefined"
      ) {
        const text = await response.text();
        for (const line of text.split("\n")) {
          yield* handleLine(line, status);
          if (finished) {
            return;
          }
        }
      } else {
        const reader = rawBody.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (value !== undefined) {
              buffer += decoder.decode(value, { stream: !done });
            }
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              yield* handleLine(line, status);
              if (finished) {
                return;
              }
            }
            if (done) {
              buffer += decoder.decode();
              if (buffer !== "") {
                yield* handleLine(buffer, status);
                if (finished) {
                  return;
                }
              }
              break;
            }
          }
        } finally {
          try {
            reader.releaseLock();
          } catch {
            /* lock already released */
          }
        }
      }
      if (!finished) {
        yield terminal();
      }
    }
    return {
      get stream_id() {
        return effectiveId;
      },
      chunks: chunks(),
    };
  }

  cancelChatStream(stream_id: string): Promise<void> {
    try {
      parseOrThrow(ChatCancelSchema, { stream_id }, 400);
    } catch {
      return Promise.reject(
        new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400),
      );
    }
    return cancelChatStreamRequest(stream_id);
  }

  readBudget(project_id: string): Promise<BudgetState> {
    return readBudgetState(project_id);
  }
}

export interface FakeApiFixtures {
  liveRows?: PartRow[];
  ledgerByProject?: Record<string, LedgerRow[]>;
  nudgeByPackage?: Record<string, PackageReport>;
  routingWhyByDecision?: Record<string, RoutingWhy>;
  projects?: ProjectRecord[];
  tasksByProject?: Record<string, TaskRecord[]>;
  budgetByProject?: Record<string, BudgetState>;
  chatDeltas?: string[];
}

export type LiveRowsListener = (rows: PartRow[]) => void;

const DEFAULT_LIVE_ROWS: PartRow[] = [
  // FAKE-OF: GET /api/v1/agents/live (K02 section 4 served PartRow list).
  { agent: "agent-1", scope: "scope-1", deliverable: "part-1", status: "RUNNING" },
  // FAKE-OF: GET /api/v1/agents/live (K02 section 4 served PartRow list).
  { agent: "agent-2", scope: "scope-2", deliverable: "part-2", status: "QUEUED" },
];

const DEFAULT_ROUTING_WHY: RoutingWhy = {
  // FAKE-OF: GET /api/v1/routing/decision/{id}/why (K04 section 4 WHY_THIS_MODEL replay).
  decision: { decision_id: "d-1", policy_ref: "pol-1" },
  // FAKE-OF: GET /api/v1/routing/decision/{id}/why (K04 section 4 assignments list).
  assignments: [],
  // FAKE-OF: GET /api/v1/routing/decision/{id}/why (K04 section 4 evidence snapshot).
  snapshot: { decision_id: "d-1", snapshot_ref: "snap-1", captured_at: "t-0" },
  // FAKE-OF: GET /api/v1/routing/decision/{id}/why (K04 section 2 ReasonText record).
  reason: {
    task_class: "tc-1",
    fit_basis: "fb-1",
    price_basis: "KNOWN",
    quality_basis: "MEASURED",
    rejected: [],
  },
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function invalidInput(): ApiError {
  return new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400);
}

function missingContext(): ApiError {
  return new ApiError("CONTEXT_MISSING", 404);
}

export class FakeApiClient implements ApiClient {
  private liveRows: PartRow[];
  private readonly ledgerByProject: Record<string, LedgerRow[]>;
  private readonly nudgeByPackage: Record<string, PackageReport>;
  private readonly routingWhyByDecision: Record<string, RoutingWhy>;
  private readonly projects: ProjectRecord[];
  private readonly tasksByProject: Record<string, TaskRecord[]>;
  private readonly budgetByProject: Record<string, BudgetState>;
  private readonly chatDeltas: string[];
  private readonly listeners = new Set<LiveRowsListener>();

  constructor(fixtures: FakeApiFixtures = {}) {
    // FAKE-OF: GET /api/v1/agents/live (K02 section 4 served PartRow list).
    this.liveRows = clone(fixtures.liveRows ?? DEFAULT_LIVE_ROWS);
    // FAKE-OF: GET /api/v1/runs/ledger (K02 section 4 stored telemetry rows).
    this.ledgerByProject = clone(fixtures.ledgerByProject ?? {
      "p-1": [
        { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
      ],
    });
    // FAKE-OF: GET /api/v1/reports/next-package-nudge (K02 C10-C11 NEW PackageReport shape).
    this.nudgeByPackage = clone(fixtures.nudgeByPackage ?? {
      "pkg-1": {
        row: { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
        nudge: "pkg-2",
        auto_push: false,
      },
    });
    // FAKE-OF: GET /api/v1/routing/decision/{id}/why (K04 section 4 WHY_THIS_MODEL replay).
    this.routingWhyByDecision = clone(fixtures.routingWhyByDecision ?? {
      "d-1": DEFAULT_ROUTING_WHY,
    });
    // FAKE-OF: GET /api/v1/projects (K13 route guard project listing).
    this.projects = clone(fixtures.projects ?? [
      { project_id: "p-1", name: "n-1", created_at: "t-0" },
    ]);
    // FAKE-OF: GET /api/v1/tasks (K13 route guard task listing).
    this.tasksByProject = clone(fixtures.tasksByProject ?? {
      "p-1": [
        {
          task_id: "t-1",
          project_id: "p-1",
          title: "n-1",
          status: "QUEUED",
          created_at: "t-0",
        },
      ],
    });
    // FAKE-OF: GET /api/v1/budget (K04 section 4 budget state).
    this.budgetByProject = clone(fixtures.budgetByProject ?? {
      "p-1": {
        project_id: "p-1",
        hard_limit: 100,
        spent: 10,
        reserved: 5,
        currency: "u-1",
      },
    });
    // FAKE-OF: POST /api/v1/chat/stream (K13 router-guard chat action class).
    this.chatDeltas = [...(fixtures.chatDeltas ?? [])];
  }

  subscribe(listener: LiveRowsListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  setLiveRows(rows: PartRow[]): void {
    // FAKE-OF: GET /api/v1/agents/live (K02 section 4 served PartRow list).
    const checked = parseAgentsLive({ agents: rows }, 200);
    this.liveRows = clone(checked);
    for (const listener of this.listeners) {
      listener(clone(this.liveRows));
    }
  }

  listAgentsLive(): Promise<PartRow[]> {
    // FAKE-OF: GET /api/v1/agents/live (K02 section 4 served PartRow list).
    return Promise.resolve(clone(this.liveRows));
  }

  readLedger(project_id: string): Promise<LedgerRow[]> {
    // FAKE-OF: GET /api/v1/runs/ledger (K02 section 4 stored telemetry rows).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const rows = this.ledgerByProject[project_id];
    if (rows === undefined) {
      return Promise.reject(missingContext());
    }
    return Promise.resolve(clone(rows));
  }

  readNextPackageNudge(package_id: string): Promise<PackageReport> {
    // FAKE-OF: GET /api/v1/reports/next-package-nudge (K02 C10-C11 NEW PackageReport shape).
    if (package_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const report = this.nudgeByPackage[package_id];
    if (report === undefined) {
      return Promise.reject(missingContext());
    }
    return Promise.resolve(clone(report));
  }

  readRoutingWhy(decision_id: string): Promise<RoutingWhy> {
    // FAKE-OF: GET /api/v1/routing/decision/{id}/why (K04 section 4 WHY_THIS_MODEL replay).
    if (decision_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const why = this.routingWhyByDecision[decision_id];
    if (why === undefined) {
      return Promise.reject(missingContext());
    }
    return Promise.resolve(clone(why));
  }

  listProjects(): Promise<ProjectRecord[]> {
    // FAKE-OF: GET /api/v1/projects (K13 route guard project listing).
    return Promise.resolve(clone(this.projects));
  }

  readProject(project_id: string): Promise<ProjectRecord> {
    // FAKE-OF: GET /api/v1/projects/{id} (K13 route guard project read).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const project = this.projects.find((row) => row.project_id === project_id);
    if (project === undefined) {
      return Promise.reject(missingContext());
    }
    return Promise.resolve(clone(project));
  }

  createProject(body: ProjectCreate): Promise<ProjectRecord> {
    // FAKE-OF: POST /api/v1/providers/connect style USER write (K13 route guard UI token check).
    const checked = ProjectCreateSchema.safeParse(body);
    if (!checked.success) {
      return Promise.reject(invalidInput());
    }
    const project: ProjectRecord = {
      project_id: `p-${this.projects.length + 1}`,
      name: checked.data.name,
      created_at: "t-0",
    };
    this.projects.push(clone(project));
    return Promise.resolve(clone(project));
  }

  updateProject(
    project_id: string,
    body: ProjectPatch,
  ): Promise<ProjectRecord> {
    // FAKE-OF: PUT /api/v1/projects/{id} (K13 route guard project write).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const checked = ProjectPatchSchema.safeParse(body);
    if (!checked.success) {
      return Promise.reject(invalidInput());
    }
    const project = this.projects.find((row) => row.project_id === project_id);
    if (project === undefined) {
      return Promise.reject(missingContext());
    }
    if (checked.data.name !== null) {
      project.name = checked.data.name;
    }
    return Promise.resolve(clone(project));
  }

  deleteProject(project_id: string): Promise<void> {
    // FAKE-OF: DELETE /api/v1/projects/{id} (K13 route guard project delete).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const index = this.projects.findIndex(
      (row) => row.project_id === project_id,
    );
    if (index < 0) {
      return Promise.reject(missingContext());
    }
    this.projects.splice(index, 1);
    return Promise.resolve();
  }

  listTasks(project_id: string): Promise<TaskRecord[]> {
    // FAKE-OF: GET /api/v1/tasks (K13 route guard task listing).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    return Promise.resolve(clone(this.tasksByProject[project_id] ?? []));
  }

  readTask(task_id: string): Promise<TaskRecord> {
    // FAKE-OF: GET /api/v1/tasks/{id} (K13 route guard task read).
    if (task_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    for (const rows of Object.values(this.tasksByProject)) {
      const task = rows.find((row) => row.task_id === task_id);
      if (task !== undefined) {
        return Promise.resolve(clone(task));
      }
    }
    return Promise.reject(missingContext());
  }

  createTask(project_id: string, body: TaskCreate): Promise<TaskRecord> {
    // FAKE-OF: POST /api/v1/tasks (K13 route guard task write).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const checked = TaskCreateSchema.safeParse(body);
    if (!checked.success) {
      return Promise.reject(invalidInput());
    }
    const existing = this.tasksByProject[project_id] ?? [];
    const task: TaskRecord = {
      task_id: `t-${existing.length + 1}`,
      project_id,
      title: checked.data.title,
      status: "QUEUED",
      created_at: "t-0",
    };
    existing.push(clone(task));
    this.tasksByProject[project_id] = existing;
    return Promise.resolve(clone(task));
  }

  openChatStream(body: ChatOpen): ChatStream {
    // FAKE-OF: POST /api/v1/chat/stream (K13 router-guard chat action class).
    const checked = ChatOpenSchema.safeParse(body);
    if (!checked.success) {
      throw invalidInput();
    }
    const streamId = checked.data.stream_id;
    const deltas = [...this.chatDeltas];
    async function* chunks(): AsyncGenerator<ChatChunk, void, void> {
      if (deltas.length === 0) {
        yield { stream_id: streamId, delta: "", done: true };
        return;
      }
      for (let index = 0; index < deltas.length; index += 1) {
        yield {
          stream_id: streamId,
          delta: deltas[index] ?? "",
          done: index === deltas.length - 1,
        };
      }
    }
    return { stream_id: streamId, chunks: chunks() };
  }

  cancelChatStream(stream_id: string): Promise<void> {
    // FAKE-OF: POST /api/v1/chat/cancel (K13 router-guard chat action class).
    if (stream_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    return Promise.resolve();
  }

  readBudget(project_id: string): Promise<BudgetState> {
    // FAKE-OF: GET /api/v1/budget (K04 section 4 budget state).
    if (project_id.length === 0) {
      return Promise.reject(invalidInput());
    }
    const state = this.budgetByProject[project_id];
    if (state === undefined) {
      return Promise.reject(missingContext());
    }
    return Promise.resolve(clone(state));
  }
}

export function validatePartRow(data: unknown): PartRow {
  const checked = PartRowSchema.safeParse(data);
  if (!checked.success) {
    throw invalidInput();
  }
  return checked.data;
}
