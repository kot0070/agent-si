// Lane A frozen API contract. Types plus declare signatures only.

export type PartStatus =
  | "QUEUED"
  | "RUNNING"
  | "RETURNED"
  | "ACCEPTED"
  | "REJECTED"
  | "BLOCKED"
  | "HANDOFF";

export interface PartRow {
  agent: string;
  scope: string;
  deliverable: string;
  status: PartStatus;
}

export interface LedgerRow {
  package_id: string;
  agents: number;
  peak_concurrency: number;
  wall_time_s: number;
}

export interface PackageLedgerRow {
  package_id: string;
  agents: number;
  peak_concurrency: number;
  wall_time_s: number;
}

export interface PackageReport {
  row: PackageLedgerRow;
  nudge: string;
  auto_push: false;
}

export type RoleMode = "PINNED" | "pool" | "AUTO";

export type PriceBasis = "KNOWN" | "UNKNOWN";

export type QualityBasis =
  | "MEASURED"
  | "STATIC_VERIFIED"
  | "UNVERIFIED_PIN"
  | "UNKNOWN";

export interface ModelRef {
  provider_id: string;
  model: string;
}

export interface CandidateView {
  provider_id: string;
  provider_instance: string | null;
  model: string;
  effective_capability_ref: string;
  price_basis: PriceBasis;
  quality_basis: QualityBasis;
  modality_ok: boolean;
  rejected: boolean;
  reject_reason: string | null;
}

export interface ReasonText {
  task_class: string;
  fit_basis: string;
  price_basis: string;
  quality_basis: string;
  rejected: string[];
}

export interface RoutingDecision {
  decision_id: string;
  policy_ref: string;
}

export interface RoutingAssignment {
  decision_id: string;
  role: string;
  provider_id: string;
  model: string;
}

export interface RoutingEvidenceSnapshot {
  decision_id: string;
  snapshot_ref: string;
  captured_at: string;
}

export interface RoutingWhy {
  decision: RoutingDecision;
  assignments: RoutingAssignment[];
  snapshot: RoutingEvidenceSnapshot;
  reason: ReasonText;
}

export interface BudgetState {
  project_id: string;
  hard_limit: number;
  spent: number;
  reserved: number;
  currency: string;
}

export interface ProjectRecord {
  project_id: string;
  name: string;
  created_at: string;
  /** SH-05: working-folder health from the project read; absent when
  the server predates the field (older rows stay unmarked). */
  folder_ok?: boolean;
  /** SH-05: resolved working folder when known (banner names it). */
  folder_path?: string;
}

export interface ProjectCreate {
  name: string;
  folder_ref: string;
}

export interface ProjectPatch {
  name: string | null;
}

export interface TaskRecord {
  task_id: string;
  project_id: string;
  title: string;
  status: string;
  created_at: string;
}

export interface TaskCreate {
  title: string;
  scope: string[];
}

export interface ChatOpen {
  project_id: string;
  prompt_ref: string;
  stream_id: string;
}

export interface ChatChunk {
  stream_id: string;
  delta: string;
  done: boolean;
  // D6(b): the typed done event of an executed engine turn carries
  // executed:true; plain answers and legacy chunks omit it. Optional so
  // every existing producer and test still typechecks unchanged.
  executed?: boolean;
}

export interface ChatStream {
  stream_id: string;
  chunks: AsyncIterable<ChatChunk>;
}

export type ApiErrorCode =
  | "SCOPE_OVERLAP"
  | "REJECTED_SCOPE_OVERLAP"
  | "GATE_NOT_PASSED"
  | "MISSING_INTEGRATION_TASK"
  | "INVALID_HIERARCHY_CHAIN"
  | "AUDIT_INDEPENDENCE_REJECTED"
  | "BUDGET_CAPPED"
  | "UNKNOWN_LIMIT_KIND"
  | "DELTA_OVER_BOUND"
  | "CONTEXT_WRONG_CONTRACT_VERSION"
  | "POLICY_CONFLICT"
  | "CONTEXT_MISSING"
  | "NO_PROFILE_BLOCKED"
  | "NO_ELIGIBLE_CANDIDATE"
  | "MODALITY_MISMATCH"
  | "PROVIDER_UNEVIDENCED"
  | "PRICE_UNKNOWN_EXPENSIVE"
  | "BUDGET_SOFT_WARN"
  | "BUDGET_HARD_BLOCKED"
  | "PENDING_RECONCILIATION"
  | "DUPLICATE_SETTLEMENT_REFUSED"
  | "KB_VALIDATION_FAILED"
  | "KB_PROPOSAL_NOT_APPROVED"
  | "KEY_SAVE_TIMEOUT"
  | "CREDENTIAL_ENTRY_MISSING"
  | "PROJECT_FOLDER_IN_USE"
  | "PROJECT_FOLDER_MISSING"
  | "NO_PROVIDER_BOUND"
  | "APPROVAL_REQUIRED";

export interface ApiErrorBody {
  code: ApiErrorCode;
  status: number;
  detail_ref: string | null;
}

export declare class ApiError extends Error {
  code: ApiErrorCode;
  status: number;
  constructor(code: ApiErrorCode, status: number);
}

export interface EndpointTable {
  readonly agentsLive: "/api/v1/agents/live";
  readonly ledger: "/api/v1/runs/ledger";
  readonly nextPackageNudge: "/api/v1/reports/next-package-nudge";
  readonly routingWhy: "/api/v1/routing/decision/{id}/why";
  readonly projects: "/api/v1/projects";
  readonly projectById: "/api/v1/projects/{id}";
  readonly tasks: "/api/v1/tasks";
  readonly taskById: "/api/v1/tasks/{id}";
  readonly chatStream: "/api/v1/chat/stream";
  readonly chatCancel: "/api/v1/chat/cancel";
  readonly budget: "/api/v1/budget";
}

export declare const ENDPOINTS: EndpointTable;

export type EndpointKey = keyof EndpointTable;

export interface ApiClient {
  listAgentsLive(): Promise<PartRow[]>;
  readLedger(project_id: string): Promise<LedgerRow[]>;
  readNextPackageNudge(package_id: string): Promise<PackageReport>;
  readRoutingWhy(decision_id: string): Promise<RoutingWhy>;
  listProjects(): Promise<ProjectRecord[]>;
  readProject(project_id: string): Promise<ProjectRecord>;
  createProject(body: ProjectCreate): Promise<ProjectRecord>;
  updateProject(project_id: string, body: ProjectPatch): Promise<ProjectRecord>;
  deleteProject(project_id: string): Promise<void>;
  listTasks(project_id: string): Promise<TaskRecord[]>;
  readTask(task_id: string): Promise<TaskRecord>;
  createTask(project_id: string, body: TaskCreate): Promise<TaskRecord>;
  openChatStream(body: ChatOpen): ChatStream;
  cancelChatStream(stream_id: string): Promise<void>;
  readBudget(project_id: string): Promise<BudgetState>;
}
