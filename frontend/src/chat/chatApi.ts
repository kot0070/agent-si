// Lane A chat area module: zod schemas plus client-driven chat stream and
// cancel calls for the chat surface. Streams open over
// POST /api/v1/chat/stream and cancel over POST /api/v1/chat/cancel
// (K02 section 4 route guard: chat POSTs carry the actor header; USER writes
// check the UI session token). The HttpApiClient performs those calls through
// requestJson/requestResponse, so this module drives the shared ApiClient
// entry, which both the HTTP client and the test client implement.

import type { ApiClient, ChatChunk, ChatOpen } from "../api/iface";
import { ApiError } from "../api/errors";
import { ChatChunkSchema, ChatOpenSchema } from "../api/projectsApi";

export { ChatChunkSchema, ChatOpenSchema };

export interface ChatProgress {
  onChunkText(text: string): void;
  isCancelled(): boolean;
}

export interface ChatRunner {
  readonly streamId: string;
  readonly done: Promise<{ aborted: boolean }>;
  cancel(): Promise<void>;
}

function invalidBody(): ApiError {
  return new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400);
}

export function streamChat(
  client: ApiClient,
  body: ChatOpen,
  progress: ChatProgress,
): ChatRunner {
  const checked = ChatOpenSchema.safeParse(body);
  if (!checked.success) {
    throw invalidBody();
  }
  const streamId = checked.data.stream_id;
  let cancelRequested = false;
  const done: Promise<{ aborted: boolean }> = (async () => {
    const stream = client.openChatStream(checked.data);
    let aborted = false;
    for await (const raw of stream.chunks) {
      if (cancelRequested || progress.isCancelled()) {
        aborted = true;
        break;
      }
      const chunk = ChatChunkSchema.safeParse(raw);
      if (!chunk.success) {
        throw invalidBody();
      }
      const data: ChatChunk = chunk.data;
      if (data.delta !== "") {
        progress.onChunkText(data.delta);
      }
      if (data.done) {
        break;
      }
    }
    return { aborted: aborted || cancelRequested };
  })();
  return {
    streamId,
    done,
    cancel(): Promise<void> {
      cancelRequested = true;
      return client.cancelChatStream(streamId);
    },
  };
}
