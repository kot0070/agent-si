// Test-only in-memory ApiClient for component tests.
// Lives under __tests__ so the product scan skips it; mirrors the
// HttpApiClient surface with canned rows validated by the same
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
} from "../iface";
import { ApiError } from "../errors";
import { parseAgentsLive } from "../agentsApi";
import {
  ChatOpenSchema,
  ProjectCreateSchema,
  ProjectPatchSchema,
  TaskCreateSchema,
} from "../projectsApi";

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
