// FXCHATHIST Part 1: app-level per-project chat store (NOT wired in).
// This module owns the chat state above routes: messages plus the live
// runner state, keyed by project, surviving component unmount (the
// module-level map outlives any mounted ChatArea). Part 2 wires
// chat/index.tsx onto it; until then index.tsx keeps component state.
// The H4 verdict line (health: ok | degraded | reconnecting) and the
// quiet dot state (online flag plus the offline queue behind the
// chat-offline-dot) are part of the per-project shape.

import { useSyncExternalStore } from "react";

export interface ChatStoredMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: number;
  final: boolean;
  decided?: "accepted" | "rejected";
  /** FXHARD1: prompt to resend (restart-interrupted turn replay). */
  resendPrompt?: string;
}

export type ChatHealth = "ok" | "degraded" | "reconnecting";

export interface ChatRunnerSnapshot {
  streamId: string | null;
  streaming: boolean;
}

export interface ProjectChatState {
  messages: ChatStoredMessage[];
  runner: ChatRunnerSnapshot;
  /** H4 verdict line: the channel health verdict. */
  health: ChatHealth;
  /** Quiet dot state: false renders the offline dot. */
  online: boolean;
  /** Quiet dot state: prompts queued while offline. */
  queue: string[];
}

export type NewChatMessage = Omit<ChatStoredMessage, "id" | "at"> & {
  id?: string;
  at?: number;
};

export type ChatMessagePatch = Partial<
  Pick<ChatStoredMessage, "text" | "final" | "decided" | "resendPrompt">
>;

let messageSeq = 0;

function nextMessageId(): string {
  messageSeq += 1;
  return `chat-store-message-${Date.now()}-${messageSeq}`;
}

function freshState(): ProjectChatState {
  return {
    messages: [],
    runner: { streamId: null, streaming: false },
    health: "ok",
    online: true,
    queue: [],
  };
}

const states = new Map<string, ProjectChatState>();
const listeners = new Map<string, Set<() => void>>();

function stateFor(projectId: string): ProjectChatState {
  let state = states.get(projectId);
  if (state === undefined) {
    state = freshState();
    states.set(projectId, state);
  }
  return state;
}

function emit(projectId: string): void {
  const watchers = listeners.get(projectId);
  if (watchers === undefined) {
    return;
  }
  for (const notify of [...watchers]) {
    notify();
  }
}

function snapshotOf(state: ProjectChatState): ProjectChatState {
  return {
    messages: state.messages.map((message) => ({ ...message })),
    runner: { ...state.runner },
    health: state.health,
    online: state.online,
    queue: [...state.queue],
  };
}

export function getChatState(projectId: string): ProjectChatState {
  return snapshotOf(stateFor(projectId));
}

export function subscribeChat(
  projectId: string,
  listener: () => void,
): () => void {
  let watchers = listeners.get(projectId);
  if (watchers === undefined) {
    watchers = new Set();
    listeners.set(projectId, watchers);
  }
  watchers.add(listener);
  return () => {
    const live = listeners.get(projectId);
    if (live !== undefined) {
      live.delete(listener);
      if (live.size === 0) {
        listeners.delete(projectId);
      }
    }
  };
}

export function appendChatMessage(
  projectId: string,
  message: NewChatMessage,
): ChatStoredMessage {
  const stored: ChatStoredMessage = {
    id: message.id ?? nextMessageId(),
    role: message.role,
    text: message.text,
    at: message.at ?? Date.now(),
    final: message.final,
    ...(message.decided === undefined ? {} : { decided: message.decided }),
    ...(message.resendPrompt === undefined
      ? {}
      : { resendPrompt: message.resendPrompt }),
  };
  stateFor(projectId).messages.push(stored);
  emit(projectId);
  return { ...stored };
}

/** FXHARD1: prepend earlier-page messages (load-earlier cursor). */
export function prependChatMessages(
  projectId: string,
  messages: NewChatMessage[],
): void {
  const state = stateFor(projectId);
  const stored = messages.map((message) => ({
    id: message.id ?? nextMessageId(),
    role: message.role,
    text: message.text,
    at: message.at ?? Date.now(),
    final: message.final,
    ...(message.decided === undefined ? {} : { decided: message.decided }),
    ...(message.resendPrompt === undefined
      ? {}
      : { resendPrompt: message.resendPrompt }),
  }));
  state.messages = [...stored, ...state.messages];
  emit(projectId);
}

export function patchChatMessage(
  projectId: string,
  id: string,
  patch: ChatMessagePatch,
): void {
  const state = stateFor(projectId);
  state.messages = state.messages.map((message) =>
    message.id === id ? { ...message, ...patch } : message,
  );
  emit(projectId);
}

export function setChatRunner(
  projectId: string,
  runner: ChatRunnerSnapshot,
): void {
  stateFor(projectId).runner = { ...runner };
  emit(projectId);
}

export function setChatHealth(projectId: string, health: ChatHealth): void {
  stateFor(projectId).health = health;
  emit(projectId);
}

export function setChatOnline(projectId: string, online: boolean): void {
  stateFor(projectId).online = online;
  emit(projectId);
}

export function enqueueChatPrompt(projectId: string, prompt: string): void {
  stateFor(projectId).queue.push(prompt);
  emit(projectId);
}

export function dequeueChatPrompt(projectId: string): string | undefined {
  const next = stateFor(projectId).queue.shift();
  emit(projectId);
  return next;
}

export function clearChatQueue(projectId: string): void {
  stateFor(projectId).queue = [];
  emit(projectId);
}

// FXUIB-B4: per-slice composer drafts. Typed text survives page change
// and remount on the same slice; a send clears it. Deliberately outside
// ProjectChatState (the store shape stays frozen) next to the other
// per-slice module maps in chat/index.tsx.
const drafts = new Map<string, string>();

export function getChatDraft(key: string): string {
  return drafts.get(key) ?? "";
}

export function setChatDraft(key: string, text: string): void {
  if (text === "") {
    drafts.delete(key);
  } else {
    drafts.set(key, text);
  }
}

export function clearChatDraft(key: string): void {
  drafts.delete(key);
}

export function resetChatStore(): void {
  states.clear();
  drafts.clear();
  messageSeq = 0;
}

/** React binding for Part 2 wiring: re-renders on this project's slice. */
export function useProjectChat(projectId: string): ProjectChatState {
  return useSyncExternalStore(
    (notify) => subscribeChat(projectId, notify),
    () => getChatState(projectId),
  );
}
