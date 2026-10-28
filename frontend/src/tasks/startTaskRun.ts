// Lane A task-run starter: opens the chat stream for a task run and records
// a session marker for it. The stream runs over POST /api/v1/chat/stream
// through the shared ApiClient entry (K02 section 4 route guard); the marker
// lives in session storage so a reload in the same session can rejoin the
// run. Production caller: wave-3 App project-tasks route
// (CODER-5-Vale frontend/src/app/App.tsx); owned test starts a run.

import { z } from "zod";
import type { ApiClient } from "../api/iface";
import { ApiError } from "../api/errors";
import { streamChat } from "../chat/chatApi";

const StartTaskRunSchema = z.object({
  projectId: z.string().min(1),
  promptRef: z.string().min(1),
  streamId: z.string().min(1),
  taskId: z.string().min(1).optional(),
});

export interface StartTaskRunInput {
  projectId: string;
  promptRef: string;
  streamId: string;
  taskId?: string;
  onText(text: string): void;
  isCancelled?(): boolean;
}

export interface TaskRunMarker {
  stream_id: string;
  project_id: string;
  task_id: string | null;
  started_at: string;
}

export interface TaskRunHandle {
  readonly streamId: string;
  readonly marker: TaskRunMarker;
  readonly done: Promise<{ aborted: boolean }>;
  cancel(): Promise<void>;
}

const MARKER_PREFIX = "agent-si.taskrun.";

const memoryMarkers = new Map<string, TaskRunMarker>();

function storeMarker(marker: TaskRunMarker): void {
  try {
    window.sessionStorage.setItem(
      MARKER_PREFIX + marker.stream_id,
      JSON.stringify(marker),
    );
  } catch {
    memoryMarkers.set(marker.stream_id, marker);
  }
}

export function readTaskRunMarker(streamId: string): TaskRunMarker | null {
  try {
    const raw = window.sessionStorage.getItem(MARKER_PREFIX + streamId);
    if (raw === null) {
      return memoryMarkers.get(streamId) ?? null;
    }
    return JSON.parse(raw) as TaskRunMarker;
  } catch {
    return memoryMarkers.get(streamId) ?? null;
  }
}

export function startTaskRun(
  client: ApiClient,
  input: StartTaskRunInput,
): TaskRunHandle {
  const checked = StartTaskRunSchema.safeParse({
    projectId: input.projectId,
    promptRef: input.promptRef,
    streamId: input.streamId,
    taskId: input.taskId,
  });
  if (!checked.success) {
    throw new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400);
  }
  const marker: TaskRunMarker = {
    stream_id: checked.data.streamId,
    project_id: checked.data.projectId,
    task_id: checked.data.taskId ?? null,
    started_at: new Date().toISOString(),
  };
  storeMarker(marker);
  const runner = streamChat(
    client,
    {
      project_id: checked.data.projectId,
      prompt_ref: checked.data.promptRef,
      stream_id: checked.data.streamId,
    },
    {
      onChunkText: input.onText,
      isCancelled: input.isCancelled ?? (() => false),
    },
  );
  return {
    streamId: runner.streamId,
    marker,
    done: runner.done,
    cancel(): Promise<void> {
      return runner.cancel();
    },
  };
}
