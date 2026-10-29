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
  const stream = client.openChatStream(checked.data);
  let cancelRequested = false;
  const done: Promise<{ aborted: boolean }> = (async () => {
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
    get streamId() {
      return stream.stream_id;
    },
    done,
    cancel(): Promise<void> {
      cancelRequested = true;
      return client.cancelChatStream(stream.stream_id);
    },
  };
}

export const CHAT_FLOOD_WINDOW_MS = 30000;
export const CHAT_FLOOD_COUNT = 4;

export function isFlooding(
  sendTimes: readonly number[],
  now: number,
): boolean {
  let recent = 0;
  for (const at of sendTimes) {
    if (now - at < CHAT_FLOOD_WINDOW_MS) {
      recent += 1;
    }
  }
  return recent >= CHAT_FLOOD_COUNT;
}

export function compactPrompt(prompt: string): string {
  return prompt.replace(/\s+/g, " ").trim().slice(0, 140);
}

export function extractChatTags(text: string): string[] {
  const pattern = /#[\p{L}\p{N}_-]+/gu;
  const tags: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (!tags.includes(match[0])) {
      tags.push(match[0]);
    }
  }
  return tags;
}
