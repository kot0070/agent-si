// Lane A ApiClient implementation: HttpApiClient over fetch.
// HttpApiClient delegates every typed call to the api area modules.

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
import { readWithSharedRetry } from "./retry";
import { listAgentsLiveRows } from "./agentsApi";
import { PartRowSchema } from "./agentsApi";
import {
  ChatCancelSchema,
  ChatOpenSchema,
  ChatStreamEventSchema,
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
    return readWithSharedRetry("agents:live", () => listAgentsLiveRows());
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
      return {
        stream_id: effectiveId,
        delta: "",
        done: true,
        // D6(b): present only for executed engine turns, so legacy and
        // plain resolutions keep their exact historical shape.
        ...(executedSeen ? { executed: true as const } : {}),
      };
    }
    let finished = false;
    // D6(b): the typed done event of an executed engine turn carries
    // executed:true. The terminal chunk forwards it only when present,
    // so legacy and plain resolutions keep their exact historical shape.
    // (Done text alone is not a signal: the served plain vocabulary
    // repeats delta text on done too, L0B-10.)
    let executedSeen = false;
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
            // FXASK2: the task-run hold arrives as a manager done event
            // with approval_requested; it raises the same tool-id ask as
            // the chat approval event so task runs get the same check.
            if (
              wire.type === "done" &&
              wire.approval_requested === true
            ) {
              throw approvalRequired(status, wire.tool_id);
            }
            if (wire.type === "done" && wire.executed === true) {
              executedSeen = true;
            }
            // FXCHATHIST engine-run verdict (minimal wire touch): the
            // autonomous dev engine ends with a done that repeats the run
            // text but carries no executed flag and no output_ref (the SSE
            // mapper only forwards present fields, and devrun data has
            // neither; the proper fix is the backend setting executed on
            // those terminals). A text-carrying done without output_ref
            // reads as the engine's own final line, so the verdict card
            // stays withheld exactly like an executed turn. Plain answers
            // keep the card: the typed plain done carries no text, and the
            // legacy done vocabulary repeats text WITH an output_ref.
            if (
              wire.type === "done" &&
              wire.executed !== true &&
              typeof wire.text === "string" &&
              wire.text !== "" &&
              typeof record["output_ref"] !== "string"
            ) {
              executedSeen = true;
            }
            finished = true;
            yield terminal();
            return;
          }
          case "error": {
            throw apiErrorFromCode(wire.code, status);
          }
          case "ask": {
            // FXASK A8: mid-stream install ask (the run waits in place).
            // Calls the ask handler and keeps reading the stream: the
            // stream never closes here. A malformed ask is ignored.
            const toolName = wire.tool_id;
            const argv = wire.argv;
            if (
              typeof toolName === "string" &&
              toolName !== "" &&
              Array.isArray(argv) &&
              argv.every((word) => typeof word === "string")
            ) {
              yield {
                stream_id: effectiveId,
                delta: "",
                done: false,
                ask: { toolName, argv },
              };
            }
            break;
          }
          case "approval": {
            // FXASK2: the approval event carries the held tool's id
            // (guard tool_name); it rides the error so the dialog and
            // POST /api/v1/permissions/check use it, once per tool.
            throw approvalRequired(status, wire.tool_id);
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

function invalidInput(): ApiError {
  return new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400);
}

// FXASK2: approval hold as an error carrying the held tool's id from
// the wire event (guard tool_name). The id travels on the error so the
// chat dialog and the task-run path run the same per-tool check.
function approvalRequired(status: number, toolId: unknown): ApiError {
  if (typeof toolId === "string" && toolId !== "") {
    return new ApiError("APPROVAL_REQUIRED", status, { toolId });
  }
  return new ApiError("APPROVAL_REQUIRED", status);
}

export function validatePartRow(data: unknown): PartRow {
  const checked = PartRowSchema.safeParse(data);
  if (!checked.success) {
    throw invalidInput();
  }
  return checked.data;
}
