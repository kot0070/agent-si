// FXCHATHIST Part 2: ChatArea wired onto the app-level per-project chat
// store (frontend/src/chat/chatStore.ts). Messages plus the live runner,
// the H4 verdict line (health) and the quiet dot state (online plus the
// offline queue) live in the module store keyed by project, so a live
// stream is NOT aborted on unmount: the module pump keeps driving the
// streamChat chunk loop into the store, and remounting (or opening the
// same project from any entry point) shows everything. History turns load
// from the served route GET /api/v1/chat/history on project open, and
// each clean completion POSTs its turn back (USER write, best effort and
// silent). Chat-first layout (messages plus composer; no graph canvas).
// Renders the prompt plus streamed tokens incrementally over the shared
// ApiClient entry; draft chip plus spinner plus timestamp; an offline queue
// dot while disconnected (prompts queue and flush on reconnect); abort
// cancels the stream cleanly. Background failures toast; blocking errors
// render inline. Channel meta shows the channel locale policy plus the tags
// served inside assistant deltas; rapid sends raise a flooding warning with
// a compact re-issue action; stream failure marks the channel degraded and
// an offline-to-online return marks it reconnecting until the next stream
// Production caller: wave-3 App chat route plus the project chat tab
// (frontend/src/app/App.tsx); owned test mounts this component.
// FXASK: install-permission dialog (F2) answers APPROVAL_REQUIRED holds via F1.

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { ReactElement } from "react";
import { z } from "zod";
import { useApiClient } from "../app/ApiClientProvider";
import type { ApiClient } from "../api/iface";
import {
  ApiError,
  apiErrorLocaleKey,
  requestJson,
  requestResponse,
} from "../api/errors";
import { DEFAULT_LOCALE, t } from "../locale/index";
import enTable from "../locale/en.json";
import { ErrorPanel } from "../ui/ErrorPanel";
import { ApprovalCard } from "./ApprovalCard";
import { HierarchyRows } from "./HierarchyRows";
import {
  appendChatMessage,
  dequeueChatPrompt,
  enqueueChatPrompt,
  getChatState,
  patchChatMessage,
  prependChatMessages,
  setChatHealth,
  setChatOnline,
  setChatRunner,
  subscribeChat,
} from "./chatStore";
import type { ProjectChatState } from "./chatStore";
import type { NewChatMessage } from "./chatStore";
import {
  CHAT_FLOOD_WINDOW_MS,
  compactPrompt,
  extractChatTags,
  isFlooding,
  streamChat,
} from "./chatApi";
import type { ChatRunner } from "./chatApi";
import {
  placementForProviderId,
  placementKey,
} from "../agents/agentsApi";
import type { Placement } from "../agents/agentsApi";
import { listConnectedProviders } from "../settings/ProvidersPage/connectApi";
import { readRoleProfiles } from "../settings/index";
import { Icon } from "../ui/icons";
import {
  askPermission,
  isInstallPermissionAsk,
  pt,
} from "./permissions";
import type { InstallPermissionAsk } from "./permissions";

export interface ChatAreaProps {
  projectId: string;
  initialDraft?: string;
  initialSend?: string;
  onSendConsumed?: () => void;
}

interface BlockingError {
  errorKey: string;
  code: string;
}

// FXCHATHIST Part 2: the store slice is session-scoped. The store itself
// is keyed by a slice key; one slice is one (project, ApiClient session)
// pair, so a remount on the same client (navigation) revives the same
// messages plus the live runner, while a fresh client (a new test, a real
// restart) starts clean and reloads from the served history route. The
// ApiClientProvider client is stable for the app lifetime, so project
// navigation never loses the slice.
const sliceOwners = new WeakMap<object, number>();
let sliceSeq = 0;

function sliceKeyFor(client: ApiClient, projectId: string): string {
  let ordinal = sliceOwners.get(client);
  if (ordinal === undefined) {
    sliceSeq += 1;
    ordinal = sliceSeq;
    sliceOwners.set(client, ordinal);
  }
  return `${projectId}#slice${ordinal}`;
}

// Slice subscription: the Part 1 useProjectChat getSnapshot mints a fresh
// object per call, which loops useSyncExternalStore for any consumer, so
// Part 2 subscribes here with normal useState batching instead (the store
// file stays untouched). Batched commits keep chunk text plus the terminal
// verdict in one observable commit, exactly like the pre-Part-2 local
// state the chat suites assert against; a sync external store would flush
// every chunk on its own and expose half-applied streams to text queries.
function useSliceState(key: string): ProjectChatState {
  const [, force] = useState(0);
  useEffect(
    () =>
      subscribeChat(key, () => {
        force((v) => v + 1);
      }),
    [key],
  );
  return getChatState(key);
}

// Slices with a mounted ChatArea. A run that finishes while its slice is
// unmounted flags the quiet unseen dot instead of showing inline UI.
const mountedSlices = new Set<string>();

// Served history load runs once per slice; the served route is the only
// turn durability across sessions. The pending permission card mirrors in
// sessionStorage for the live session only (never turn storage).
const historyLoading = new Set<string>();
const historyLoaded = new Set<string>();

// Live module pumps: one streamChat driver per slice. The pump outlives
// any mounted ChatArea (H1: unmount never cancels); completion writes the
// final text plus the health verdict into the store.
interface ChatPump {
  cancelled: boolean;
  runner: ChatRunner;
  prompt: string;
  assistantId: string;
}

const pumps = new Map<string, ChatPump>();

// Executed engine turns (done event with executed:true) hide the verdict
// card (D6(b), FXDESIGN6). The store shape is frozen, so the per-message
// engine flag lives here, keyed by the unique store message id.
const engineRunMessages = new Set<string>();

// Assistant placeholders pruned after a failed stream (the store is
// append/patch only). Render filters these ids out.
const deadAssistants = new Set<string>();

// Last sent prompt per slice (retry plus compact resend survive remount).
const lastSentBySlice = new Map<string, string>();

// Send timestamps per slice (flood window survives remount).
const sendTimesBySlice = new Map<string, number[]>();

// Opening run id per slice (permission Allow replays the same run).
const runIdBySlice = new Map<string, string>();

// Single blocking error delivery: a mounted ChatArea registers its
// setters; a completion while unmounted stashes the error for the next
// mount, so the single error card (S5) is never lost nor doubled.
interface SliceUI {
  onBlocking(error: BlockingError | null): void;
  onAsk(ask: InstallPermissionAsk | null): void;
}

const sliceUI = new Map<string, SliceUI>();
const blockingStash = new Map<string, BlockingError>();
const askStash = new Map<string, InstallPermissionAsk>();

// FXHARD1: the pending card may mirror in sessionStorage for the live
// session only (the served store is the server: the origin port changes
// per launch, so localStorage is never a store here). Leaving the page
// restores from the stash or the mirror; a restart shows the served
// running turn as interrupted with a resend instead.
function askMirrorKey(key: string): string {
  return `fxchat.ask.${key}`;
}

function readAskMirror(key: string): InstallPermissionAsk | null {
  try {
    const raw = window.sessionStorage.getItem(askMirrorKey(key));
    if (raw === null) {
      return null;
    }
    const parsed = JSON.parse(raw) as {
      toolName?: unknown;
      messageId?: unknown;
    };
    if (
      typeof parsed.toolName === "string" &&
      parsed.toolName !== "" &&
      typeof parsed.messageId === "string" &&
      parsed.messageId !== ""
    ) {
      return { toolName: parsed.toolName, messageId: parsed.messageId };
    }
    return null;
  } catch {
    return null;
  }
}

function writeAskMirror(key: string, ask: InstallPermissionAsk | null): void {
  try {
    if (ask === null) {
      window.sessionStorage.removeItem(askMirrorKey(key));
      return;
    }
    window.sessionStorage.setItem(
      askMirrorKey(key),
      JSON.stringify({ toolName: ask.toolName, messageId: ask.messageId }),
    );
  } catch {
    return;
  }
}

function stashAsk(key: string, ask: InstallPermissionAsk): void {
  askStash.set(key, ask);
  writeAskMirror(key, ask);
}

function consumeAskStash(key: string): InstallPermissionAsk | null {
  const stashed = askStash.get(key);
  if (stashed !== undefined) {
    askStash.delete(key);
    return stashed;
  }
  return readAskMirror(key);
}

function clearAskStash(key: string): void {
  askStash.delete(key);
  writeAskMirror(key, null);
}

function consumeBlockingStash(key: string): BlockingError | null {
  const stashed = blockingStash.get(key);
  if (stashed !== undefined) {
    blockingStash.delete(key);
    return stashed;
  }
  return null;
}

function emitBlocking(key: string, error: BlockingError): void {
  const ui = sliceUI.get(key);
  if (ui !== undefined) {
    ui.onBlocking(error);
    return;
  }
  blockingStash.set(key, error);
}

function clearSliceBlocking(key: string): void {
  blockingStash.delete(key);
  sliceUI.get(key)?.onBlocking(null);
}

function emitAsk(key: string, ask: InstallPermissionAsk): void {
  const ui = sliceUI.get(key);
  if (ui !== undefined) {
    ui.onAsk(ask);
    return;
  }
  stashAsk(key, ask);
}

// H4 quiet dot: slices whose run finished while no ChatArea showed them.
// Opening the chat (mount) clears it; the verdict line stays in the store.
const unseenSlices = new Set<string>();
const unseenListeners = new Set<() => void>();
let unseenVersion = 0;

function emitUnseen(): void {
  unseenVersion += 1;
  for (const notify of [...unseenListeners]) {
    notify();
  }
}

function flagChatUnseen(key: string): void {
  if (mountedSlices.has(key)) {
    return;
  }
  if (!unseenSlices.has(key)) {
    unseenSlices.add(key);
    emitUnseen();
  }
}

function markSeenByKey(key: string): void {
  if (unseenSlices.delete(key)) {
    emitUnseen();
  }
}

/** H4 quiet dot: true while this project's chat holds unseen activity. */
export function hasChatUnseen(client: ApiClient, projectId: string): boolean {
  return unseenSlices.has(sliceKeyFor(client, projectId));
}

/** Opening a project's chat clears its quiet dot. */
export function markChatSeen(client: ApiClient, projectId: string): void {
  markSeenByKey(sliceKeyFor(client, projectId));
}

/** Re-renders project rows when any quiet dot changes. */
export function useUnseenVersion(): number {
  return useSyncExternalStore(
    (notify) => {
      unseenListeners.add(notify);
      return () => {
        unseenListeners.delete(notify);
      };
    },
    () => unseenVersion,
  );
}

// Served chat history (FXCHATHIST Part 1 route, read oldest-first).
const CHAT_HISTORY_ROUTE = "/api/v1/chat/history";

function historyPath(projectId: string): string {
  return `${CHAT_HISTORY_ROUTE}?project_id=${encodeURIComponent(projectId)}`;
}

const ChatHistoryTurnSchema = z.object({
  project_id: z.string(),
  user_text: z.string(),
  assistant_text: z.string(),
  time: z.string(),
  id: z.string().optional().default(""),
  status: z.string().optional().default("ok"),
  run_id: z.string().optional().default(""),
  error_code: z.string().optional().default(""),
});

const ChatHistoryResponseSchema = z.object({
  turns: z.array(ChatHistoryTurnSchema),
  next_before: z.string().nullable().optional(),
  total: z.number().optional(),
});

type ChatHistoryPage = z.infer<typeof ChatHistoryResponseSchema>;

// Earlier-page cursor per slice (None after the oldest page loads).
const historyCursors = new Map<string, string | null>();

async function fetchHistoryPage(
  projectId: string,
  before?: string,
): Promise<ChatHistoryPage> {
  const path =
    before !== undefined && before !== ""
      ? `${historyPath(projectId)}&before=${encodeURIComponent(before)}`
      : historyPath(projectId);
  return requestJson(path, { method: "GET", kind: "read" },
    ChatHistoryResponseSchema);
}

/** FXHARD1: interrupted-restart line (never Working: runner stays idle). */
function interruptedText(stored: string): string {
  const note = pt(
    "chat.stream.interrupted",
    "Interrupted when the app closed",
  );
  return stored !== "" ? `${stored}\n${note}` : note;
}

// Merge one served page into the slice, oldest first. Merge key is the
// server turn id only: identical user texts ("hello" twice) never drop
// nor duplicate. A running turn whose stream is gone renders as
// interrupted with its stored text plus a resend; failed and stopped
// turns restore the error card.
function buildHistoryBatch(
  key: string,
  page: ChatHistoryPage,
): { batch: NewChatMessage[]; sawTerminal: boolean } {
  const known = new Set(
    getChatState(key).messages.map((message) => message.id),
  );
  const batch: NewChatMessage[] = [];
  let sawTerminal = false;
  for (const turn of page.turns) {
    const tid =
      turn.id !== "" ? turn.id : `${turn.time}::${turn.user_text}`;
    const userId = `hist-user-${tid}`;
    const assistantId = `hist-asst-${tid}`;
    if (known.has(userId) || known.has(assistantId)) {
      continue;
    }
    known.add(userId);
    known.add(assistantId);
    const parsed = Date.parse(turn.time);
    const at = Number.isNaN(parsed) ? Date.now() : parsed;
    if (turn.status === "running") {
      batch.push({
        id: userId,
        role: "user",
        text: turn.user_text,
        at,
        final: true,
      });
      batch.push({
        id: assistantId,
        role: "assistant",
        text: interruptedText(turn.assistant_text),
        at,
        final: true,
        resendPrompt: turn.user_text,
      });
      continue;
    }
    batch.push({
      id: userId,
      role: "user",
      text: turn.user_text,
      at,
      final: true,
    });
    if (turn.assistant_text !== "") {
      batch.push({
        id: assistantId,
        role: "assistant",
        text: turn.assistant_text,
        at,
        final: true,
      });
    }
    if (turn.status === "failed" || turn.status === "stopped") {
      sawTerminal = true;
      emitBlocking(key, {
        errorKey: apiErrorLocaleKey(turn.error_code || "UNKNOWN"),
        code: turn.error_code !== "" ? turn.error_code : "UNKNOWN",
      });
    }
  }
  return { batch, sawTerminal };
}

function applyHistoryBatch(
  key: string,
  page: ChatHistoryPage,
  mode: "append" | "prepend",
): void {
  const { batch, sawTerminal } = buildHistoryBatch(key, page);
  if (mode === "prepend") {
    prependChatMessages(key, batch);
  } else {
    for (const message of batch) {
      appendChatMessage(key, message);
    }
  }
  if (sawTerminal) {
    setChatHealth(key, "degraded");
  }
  if (page.next_before !== undefined && page.next_before !== null) {
    historyCursors.set(key, page.next_before);
  } else {
    historyCursors.delete(key);
  }
}

function mergeHistoryPage(key: string, page: ChatHistoryPage): void {
  applyHistoryBatch(key, page, "append");
}

async function loadHistoryOnce(key: string, projectId: string): Promise<string | null> {
  if (historyLoaded.has(key) || historyLoading.has(key)) {
    return historyCursors.get(key) ?? null;
  }
  historyLoading.add(key);
  try {
    const page = await fetchHistoryPage(projectId);
    mergeHistoryPage(key, page);
    return historyCursors.get(key) ?? null;
  } catch {
    // History is best effort: a failed load never breaks the composer.
    return null;
  } finally {
    historyLoading.delete(key);
    historyLoaded.add(key);
  }
}

/** Bubble timestamps read time-only ("14:32"), never the date. */
function formatChatTime(at: number): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(at));
  } catch {
    return new Date(at).toLocaleTimeString();
  }
}

// Best-effort turn persist (USER write). A failed POST never surfaces.
// The running write opens the run (upsert key: run id); the terminal
// write (ok / failed / stopped) closes the same turn server-side.
async function recordTurnBestEffort(
  projectId: string,
  userText: string,
  assistantText: string,
  extra?: { status?: string; run_id?: string; error_code?: string },
): Promise<void> {
  try {
    await requestResponse(CHAT_HISTORY_ROUTE, {
      method: "POST",
      kind: "write",
      body: {
        project_id: projectId,
        user_text: userText,
        assistant_text: assistantText,
        status: extra?.status ?? "ok",
        run_id: extra?.run_id ?? "",
        error_code: extra?.error_code ?? "",
      },
    });
  } catch {
    return;
  }
}

let streamSeq = 0;

function nextStreamId(): string {
  streamSeq += 1;
  return `chat-stream-${Date.now()}-${streamSeq}`;
}

function readOnline(): boolean {
  if (typeof navigator !== "undefined" && typeof navigator.onLine === "boolean") {
    return navigator.onLine;
  }
  return true;
}

function readChannelLocale(): string {
  // FXASK F2: no browser persistent storage in chat files. The active
  // locale is probed through the locale table instead (the en table is
  // read-only input here, never edited).
  try {
    const probe = t("settings.general.title");
    const table = enTable as unknown as {
      settings?: { general?: { title?: unknown } };
    };
    if (
      table.settings !== undefined &&
      table.settings.general !== undefined &&
      table.settings.general.title === probe
    ) {
      return "en";
    }
  } catch {
    return DEFAULT_LOCALE;
  }
  return "uk";
}

/** Bound chat models for the pre-send hint (GET only, never a token). */
const CHAT_MODELS_ROUTE = "/api/v1/chat/models";

/** FXASKB B2: the devrun-hold decision ledger (A2 route, token-guarded). */
const PERMISSIONS_DECIDE_ROUTE = "/api/v1/permissions/decide";

/** FXASKB B3: one journal row per recorded chat answer (token-guarded). */
const CHAT_DECISION_ROUTE = "/api/v1/chat/decision";

function isInstallHoldTool(toolName: string): boolean {
  // A B1 hold id names the held command (install:<project>:<argv0>); the
  // legacy guard-tool asks keep the asked-once check path.
  return toolName.startsWith("install:");
}

async function readBoundModels(projectId: string): Promise<unknown[] | null> {
  try {
    const response = await fetch(
      `${CHAT_MODELS_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
    );
    if (!response.ok) {
      return null;
    }
    const body = (await response.json()) as { models?: unknown };
    return Array.isArray(body.models) ? body.models : [];
  } catch {
    // Unknown binding: no hint either way, the post-send error still applies.
    return null;
  }
}

function runErrorCode(error: unknown): string {
  return error instanceof ApiError ? error.code : "UNKNOWN";
}

function handleRunError(
  key: string,
  assistantId: string,
  error: unknown,
  record?: { projectId: string; prompt: string; runId: string },
): void {
  if (isInstallPermissionAsk(error)) {
    // FXASK2: the run is held for install permission (served
    // approval event). The held message stays final so the answer is
    // recorded on the run; the F1 ask-once ledger decides whether the
    // dialog shows at all. The tool is the event's own tool id
    // (guard tool_name), answered once per tool — never a
    // project-derived key.
    patchChatMessage(key, assistantId, { final: true });
    const toolName = (error as ApiError).toolId as string;
    if (isInstallHoldTool(toolName)) {
      // FXASKB B1 hold: the dialog shows regardless of the
      // asked-once flag; Allow/Deny records the decision and the
      // same prompt resends, so the run continues stored and
      // never asks again. The tool is the command's own id.
      emitAsk(key, { toolName, messageId: assistantId });
      return;
    }
    void askPermission(toolName).then(
      (outcome) => {
        if (!outcome.askedOnce) {
          emitAsk(key, { toolName, messageId: assistantId });
        }
      },
      () => {
        emitAsk(key, { toolName, messageId: assistantId });
      },
    );
    return;
  }
  const current = getChatState(key).messages.find(
    (message) => message.id === assistantId,
  );
  if (record !== undefined) {
    // Failed runs are stored too (holds are not terminal: Allow replays
    // the same run id, so the held running turn upserts into one turn).
    const partial = current?.text ?? "";
    void recordTurnBestEffort(record.projectId, record.prompt, partial, {
      status: "failed",
      run_id: record.runId,
      error_code: runErrorCode(error),
    });
  }
  if (current !== undefined && current.text === "") {
    // Failed before any token: prune the empty placeholder (render
    // filters pruned ids, the store stays append/patch only).
    deadAssistants.add(assistantId);
  } else {
    patchChatMessage(key, assistantId, { final: false });
  }
  setChatHealth(key, "degraded");
  if (error instanceof ApiError) {
    emitBlocking(key, {
      errorKey: apiErrorLocaleKey(error.code),
      code: error.code,
    });
  } else {
    emitBlocking(key, { errorKey: "errors.generic", code: "UNKNOWN" });
  }
}

/**
 * Module pump: starts one streamChat driver per slice and folds every
 * chunk plus the terminal verdict into the store. Survives unmount (H1);
 * a second call while the slice streams is a no-op (double-mount guard).
 * FXHARD1: the run start stores a running turn (user text + run id);
 * every terminal event closes it (ok / failed / stopped), so the UI
 * always leaves Working and restarts show interrupt, never Working.
 * Replays (permission Allow/Deny) reuse the opening run id and skip
 * the user copy: one visible user turn per prompt.
 */
function startChatRun(
  client: ApiClient,
  projectId: string,
  prompt: string,
  opts?: {
    skipUserAppend?: boolean;
    runId?: string;
  },
): void {
  const key = sliceKeyFor(client, projectId);
  const text = prompt.trim();
  if (text === "") {
    return;
  }
  if (pumps.has(key) || getChatState(key).runner.streaming) {
    return;
  }
  clearSliceBlocking(key);
  lastSentBySlice.set(key, text);
  const at = Date.now();
  // Replays (permission Allow/Deny) keep the opening run id so the
  // terminal write upserts the held running turn: one stored turn per run.
  const runId = opts?.runId ?? nextStreamId();
  runIdBySlice.set(key, runId);
  if (opts?.skipUserAppend !== true) {
    appendChatMessage(key, { role: "user", text, at, final: true });
  }
  // Replays stream the answer into a fresh bubble; the held message
  // keeps only the permission receipt (no user + assistant copies, one
  // visible user turn per prompt).
  const assistantId = appendChatMessage(key, {
    role: "assistant",
    text: "",
    at,
    final: false,
  }).id;
  // The running turn opens the run; the terminal write below upserts
  // the same run id, so each run leaves exactly one stored turn.
  void recordTurnBestEffort(projectId, text, "", {
    status: "running",
    run_id: runId,
  });
  const streamId = runId;
  setChatRunner(key, { streamId, streaming: true });
  let runner: ChatRunner;
  try {
    runner = streamChat(
      client,
      { project_id: projectId, prompt_ref: text, stream_id: streamId },
      {
        onChunkText: (delta) => {
          const current = getChatState(key).messages.find(
            (message) => message.id === assistantId,
          );
          if (current !== undefined) {
            patchChatMessage(key, assistantId, {
              text: current.text + delta,
            });
          }
        },
        isCancelled: () => pumps.get(key)?.cancelled ?? true,
      },
    );
  } catch (error) {
    setChatRunner(key, { streamId: null, streaming: false });
    handleRunError(key, assistantId, error, {
      projectId,
      prompt: text,
      runId,
    });
    if (!mountedSlices.has(key)) {
      flagChatUnseen(key);
    }
    return;
  }
  pumps.set(key, {
    cancelled: false,
    runner,
    prompt: text,
    assistantId,
  });
  runner.done.then(
    ({ aborted, executed }) => {
      pumps.delete(key);
      setChatRunner(key, { streamId: null, streaming: false });
      const answer =
        getChatState(key).messages.find(
          (message) => message.id === assistantId,
        )?.text ?? "";
      if (aborted) {
        // Stop closes the run as stopped: stored, never Working.
        patchChatMessage(key, assistantId, { final: false });
        void recordTurnBestEffort(projectId, text, answer, {
          status: "stopped",
          run_id: runId,
          error_code: "STOPPED",
        });
      } else if (answer === "") {
        // Dropped stream (no terminal text): a clear failed line.
        patchChatMessage(key, assistantId, { final: false });
        setChatHealth(key, "degraded");
        void recordTurnBestEffort(projectId, text, answer, {
          status: "failed",
          run_id: runId,
          error_code: "EMPTY_RESPONSE",
        });
        emitBlocking(key, {
          errorKey: apiErrorLocaleKey("UNKNOWN"),
          code: "UNKNOWN",
        });
      } else {
        setChatHealth(key, "ok");
        patchChatMessage(key, assistantId, { final: true });
        if (executed === true) {
          engineRunMessages.add(assistantId);
        }
        void recordTurnBestEffort(projectId, text, answer, {
          status: "ok",
          run_id: runId,
        });
      }
      if (!mountedSlices.has(key)) {
        flagChatUnseen(key);
      }
    },
    (error: unknown) => {
      pumps.delete(key);
      setChatRunner(key, { streamId: null, streaming: false });
      handleRunError(key, assistantId, error, {
        projectId,
        prompt: text,
        runId,
      });
      if (!mountedSlices.has(key)) {
        flagChatUnseen(key);
      }
    },
  );
}

export function ChatArea(props: ChatAreaProps): ReactElement {
  const client = useApiClient();
  const key = sliceKeyFor(client, props.projectId);
  // The slice is the render truth: messages, the live runner, the H4
  // verdict line and the quiet dot state all survive unmount here.
  const chatState = useSliceState(key);
  const messages = chatState.messages.filter(
    (message) => !deadAssistants.has(message.id),
  );
  const streaming = chatState.runner.streaming;
  const health = chatState.health;
  const online = chatState.online;
  const queue = chatState.queue;
  const [boundModels, setBoundModels] = useState<unknown[] | null>(null);
  const [connected, setConnected] = useState<string[] | null>(null);
  const [directorModel, setDirectorModel] = useState<string | null>(null);
  const [draft, setDraft] = useState(props.initialDraft ?? "");
  const [blocking, setBlocking] = useState<BlockingError | null>(() =>
    consumeBlockingStash(key),
  );
  const [toast, setToast] = useState<string | null>(null);
  const [flooded, setFlooded] = useState(false);
  const offlineRef = useRef(!readOnline());
  const oneShotSentRef = useRef(false);
  const [pendingAsk, setPendingAsk] = useState<InstallPermissionAsk | null>(
    null,
  );
  // FXHARD1: earlier-page cursor from the served history page (null at
  // the oldest turn) plus the load-earlier busy flag.
  const [cursor, setCursor] = useState<string | null>(null);
  const [earlierBusy, setEarlierBusy] = useState(false);
  const pendingAskRef = useRef<InstallPermissionAsk | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  // FXRC1FIX P3: the message list owns the scroll inside the chat card;
  // the composer sits below it in flow and never overlays text. stick
  // follows the newest message unless the user scrolled up.
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);

  function dismissToast(): void {
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
    setToast(null);
  }

  function showToast(text: string): void {
    // S5: toasts are transient: one visible at a time, gone after 5 s.
    setToast(text);
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 5000);
  }

  // Slice identity: opening the chat clears its quiet dot (H4), mirrors
  // the device online state into the slice, loads served turns (H2) and
  // registers this mount for inline error plus permission UI. Unmount only
  // detaches: the pump keeps streaming into the store (H1).
  useEffect(() => {
    mountedSlices.add(key);
    markSeenByKey(key);
    const stashedBlocking = consumeBlockingStash(key);
    if (stashedBlocking !== null) {
      setBlocking(stashedBlocking);
    }
    setPendingAsk(null);
    pendingAskRef.current = null;
    const stashedAsk = consumeAskStash(key);
    if (stashedAsk !== null) {
      pendingAskRef.current = stashedAsk;
      setPendingAsk(stashedAsk);
    }
    const ui: SliceUI = {
      onBlocking: (error) => {
        setBlocking(error);
      },
      onAsk: (ask) => {
        pendingAskRef.current = ask;
        setPendingAsk(ask);
      },
    };
    sliceUI.set(key, ui);
    setChatOnline(key, readOnline());
    void loadHistoryOnce(key, props.projectId).then((next) => {
      setCursor(next);
    });
    return () => {
      mountedSlices.delete(key);
      // Leaving the page keeps the pending card: stash (plus the
      // live-session mirror) so the return restores the same dialog.
      if (pendingAskRef.current !== null) {
        stashAsk(key, pendingAskRef.current);
      }
      if (sliceUI.get(key) === ui) {
        sliceUI.delete(key);
      }
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = null;
      }
    };
  }, [key, props.projectId]);

  useEffect(() => {
    const onOnline = (): void => {
      setChatOnline(key, true);
      if (offlineRef.current) {
        offlineRef.current = false;
        setChatHealth(key, "reconnecting");
      }
    };
    const onOffline = (): void => {
      offlineRef.current = true;
      setChatOnline(key, false);
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [key]);

  useEffect(() => {
    let alive = true;
    void readBoundModels(props.projectId).then((models) => {
      if (alive) {
        setBoundModels(models);
      }
    });
    return () => {
      alive = false;
    };
  }, [props.projectId]);

  // FXDESIGN6: the status line under the composer names the same model and
  // route the hierarchy rows and the top bar show (served records only).
  useEffect(() => {
    let alive = true;
    void listConnectedProviders().then((ids) => {
      if (alive) {
        setConnected(ids);
      }
    });
    void readRoleProfiles(props.projectId).then(
      (profiles) => {
        if (!alive) {
          return;
        }
        const director = profiles.director;
        if (
          director !== undefined &&
          director.mode === "PINNED" &&
          director.provider !== undefined &&
          director.model !== undefined
        ) {
          setDirectorModel(`${director.provider} — ${director.model}`);
        } else {
          setDirectorModel(null);
        }
      },
      () => {
        if (alive) {
          setDirectorModel(null);
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [props.projectId]);

  function statusRoute(): string {
    if (connected === null || connected.length === 0) {
      return t("shell.common.unknown");
    }
    const route = new Set<Placement>();
    for (const id of connected) {
      route.add(placementForProviderId(id));
    }
    if (route.size === 1) {
      const only = [...route][0];
      return only === undefined ? t("shell.common.unknown") : t(placementKey(only));
    }
    return t(placementKey("SPLIT"));
  }

  // First-message one-shot: the start box created the project plus
  // task already, so the kept message sends once through the module
  // pump on mount, guarded against double effects, then the
  // parent clears it. initialDraft keeps filling without sending.
  useEffect(() => {
    if (
      props.initialSend !== undefined &&
      props.initialSend !== "" &&
      !oneShotSentRef.current
    ) {
      oneShotSentRef.current = true;
      startChatRun(client, props.projectId, props.initialSend);
      props.onSendConsumed?.();
    }
    // One-shot only: the sent guard covers double effects.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (online && !streaming && queue.length > 0) {
      const next = queue[0];
      if (next === undefined) {
        return;
      }
      dequeueChatPrompt(key);
      dismissToast();
      startChatRun(client, props.projectId, next);
    }
  });

  function handleSendPrompt(prompt: string): void {
    const text = prompt.trim();
    if (text === "" || streaming) {
      return;
    }
    dismissToast();
    const sentAt = Date.now();
    const previous = sendTimesBySlice.get(key) ?? [];
    const recentSends = [
      ...previous.filter((at) => sentAt - at < CHAT_FLOOD_WINDOW_MS),
      sentAt,
    ];
    sendTimesBySlice.set(key, recentSends);
    if (isFlooding(recentSends, sentAt)) {
      setFlooded(true);
    }
    startChatRun(client, props.projectId, text);
  }

  const handleSend = (): void => {
    const prompt = draft.trim();
    if (prompt === "" || streaming) {
      return;
    }
    if (!online) {
      enqueueChatPrompt(key, prompt);
      setDraft("");
      showToast(t("chat.stream.offline"));
      return;
    }
    setDraft("");
    handleSendPrompt(prompt);
  };

  const handleAbort = (): void => {
    const pump = pumps.get(key);
    if (pump === undefined) {
      return;
    }
    pump.cancelled = true;
    pump.runner.cancel().then(
      () => undefined,
      () => {
        showToast(t("errors.generic"));
      },
    );
  };

  const handleRetry = (): void => {
    const prompt = lastSentBySlice.get(key) ?? null;
    if (prompt === null || streaming) {
      return;
    }
    clearSliceBlocking(key);
    setBlocking(null);
    if (!online) {
      enqueueChatPrompt(key, prompt);
      return;
    }
    handleSendPrompt(prompt);
  };

  // FXHARD1: earlier history page (prepends, never disturbs the pump).
  async function handleLoadEarlier(): Promise<void> {
    if (cursor === null || earlierBusy) {
      return;
    }
    setEarlierBusy(true);
    try {
      const page = await fetchHistoryPage(props.projectId, cursor);
      applyHistoryBatch(key, page, "prepend");
      setCursor(historyCursors.get(key) ?? null);
    } catch {
      return;
    } finally {
      setEarlierBusy(false);
    }
  }

  const handleCompactResend = (): void => {    const prompt = lastSentBySlice.get(key) ?? null;
    if (prompt === null || streaming) {
      return;
    }
    const compacted = compactPrompt(prompt);
    sendTimesBySlice.set(key, []);
    setFlooded(false);
    clearSliceBlocking(key);
    setBlocking(null);
    if (!online) {
      enqueueChatPrompt(key, compacted);
      return;
    }
    // The compacted prompt bypasses the flood window it just cleared.
    startChatRun(client, props.projectId, compacted);
  };

  const answerAsk = (allow: boolean): void => {
    const ask = pendingAskRef.current;
    if (ask === null) {
      return;
    }
    pendingAskRef.current = null;
    setPendingAsk(null);
    clearAskStash(key);
    if (isInstallHoldTool(ask.toolName)) {
      // FXASKB B2: record the decision with the session token, then
      // resend the same prompt automatically; the stored answer lets
      // the run continue without asking again.
      const decision = allow ? "allow" : "deny";
      void requestResponse(PERMISSIONS_DECIDE_ROUTE, {
        method: "POST",
        kind: "write",
        body: {
          tool_id: ask.toolName,
          decision,
          project_id: props.projectId,
        },
      }).then(
        () => {
          const note = allow
            ? pt(
                "chat.permission.allowed",
                "Install permission granted for '{tool}'.",
                { tool: ask.toolName },
              )
            : pt(
                "chat.permission.denied",
                "Install permission denied for '{tool}'.",
                { tool: ask.toolName },
              );
          const current = getChatState(key).messages.find(
            (message) => message.id === ask.messageId,
          );
          if (current !== undefined) {
            patchChatMessage(key, ask.messageId, {
              text:
                current.text === "" ? note : `${current.text}\n${note}`,
              decided: allow ? "accepted" : "rejected",
            });
          }
          const prompt = lastSentBySlice.get(key) ?? null;
          // Replay once, one visible user turn: the decision is recorded,
          // then the same prompt resends without the user copy (the held
          // message keeps only the receipt; the terminal write upserts
          // the opening run id into one stored turn).
          if (prompt !== null) {
            const replayRunId = runIdBySlice.get(key);
            startChatRun(client, props.projectId, prompt, {
              skipUserAppend: true,
              ...(replayRunId === undefined ? {} : { runId: replayRunId }),
            });
          }
        },
        () => {
          emitBlocking(key, { errorKey: "errors.generic", code: "UNKNOWN" });
        },
      );
      return;
    }
    void askPermission(ask.toolName).then(
      () => {
        const note = allow
          ? pt(
              "chat.permission.allowed",
              "Install permission granted for '{tool}'.",
              { tool: ask.toolName },
            )
          : pt(
              "chat.permission.denied",
              "Install permission denied for '{tool}'.",
              { tool: ask.toolName },
            );
        const current = getChatState(key).messages.find(
          (message) => message.id === ask.messageId,
        );
        if (current !== undefined) {
          patchChatMessage(key, ask.messageId, {
            text: current.text === "" ? note : `${current.text}\n${note}`,
            decided: allow ? "accepted" : "rejected",
          });
        }
      },
      () => {
        emitBlocking(key, { errorKey: "errors.generic", code: "UNKNOWN" });
      },
    );
  };

  const decide = (id: string, decided: "accepted" | "rejected"): void => {
    const proposal =
      getChatState(key).messages.find((message) => message.id === id)?.text ??
      "";
    patchChatMessage(key, id, { decided });
    // FXASKB B3: Accept and Reject each post one journal row through
    // the token-guarded route; a failed post never blocks the local
    // decision.
    void requestResponse(CHAT_DECISION_ROUTE, {
      method: "POST",
      kind: "write",
      body: {
        project_id: props.projectId,
        decision: decided,
        proposal: proposal.slice(0, 500),
      },
    }).then(
      () => undefined,
      () => undefined,
    );
  };

  // FXRC1FIX P3: follow new text only while the user stays pinned
  // to the newest message; a manual scroll-up keeps its position.
  useEffect(() => {
    if (!stickRef.current) {
      return;
    }
    const box = messagesRef.current;
    if (box === null) {
      return;
    }
    box.scrollTop = box.scrollHeight;
  }, [messages, streaming]);

  function handleMessagesScroll(): void {
    const box = messagesRef.current;
    if (box === null) {
      return;
    }
    stickRef.current =
      box.scrollHeight - box.scrollTop - box.clientHeight < 24;
  }

  const channelLocale = readChannelLocale();
  const channelTags = messages.flatMap((message) =>
    message.role === "assistant" ? extractChatTags(message.text) : [],
  );
  const visibleTags = [...new Set(channelTags)];

  return (
    <section data-testid="chat-area" aria-label={t("shell.sidebar.chat")}>
      {/* FXDESIGN6: the ref centre carries no card and no "Chat" heading;
          the h1 stays in the DOM for the frozen heading contract but reads
          as plain conversation (visually hidden). */}
      <h1 className="fx-vh">{t("shell.sidebar.chat")}</h1>
      <HierarchyRows projectId={props.projectId} />
      <div
        data-testid="chat-layout"
        style={{ maxHeight: "calc(100vh - 200px)" }}
      >
        <div
          data-testid="chat-messages"
          ref={messagesRef}
          onScroll={handleMessagesScroll}
          className="fx-chat-column"
        >
          {cursor !== null ? (
            <button
              type="button"
              data-testid="chat-load-earlier"
              className="fx-btn-quiet"
              disabled={earlierBusy}
              onClick={() => {
                void handleLoadEarlier();
              }}
            >
              {pt("chat.stream.loadEarlier", "Load earlier")}
            </button>
          ) : null}
          {messages.map((message) => (
            <div
              key={message.id}
              data-testid={
                message.role === "user"
                  ? "chat-user-message"
                  : "chat-assistant-message"
              }
              className={
                message.role === "user"
                  ? "fx-msg fx-msg-user"
                  : "fx-msg fx-msg-assistant"
              }
            >
              <p style={{ whiteSpace: "pre-wrap" }}>{message.text}</p>
              <time
                data-testid="chat-timestamp"
                title={t("chat.stream.timestamp")}
              >
                {formatChatTime(message.at)}
              </time>
              {message.resendPrompt !== undefined ? (
                <button
                  type="button"
                  data-testid="chat-resend"
                  className="fx-btn-quiet"
                  onClick={() => {
                    startChatRun(
                      client,
                      props.projectId,
                      message.resendPrompt ?? "",
                    );
                  }}
                >
                  {pt("chat.stream.resend", "Resend")}
                </button>
              ) : null}
              {message.role === "assistant" &&
              message.final &&
              message.text !== "" &&
              message.decided === undefined &&
              !engineRunMessages.has(message.id) &&
              !streaming ? (
                <ApprovalCard
                  proposal={message.text}
                  onAccept={() => {
                    decide(message.id, "accepted");
                  }}
                  onEdit={(next) => {
                    setDraft(next);
                  }}
                  onReject={() => {
                    decide(message.id, "rejected");
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>
        {visibleTags.length > 0 ? (
          <div data-testid="chat-channel-meta">
            <span
              data-testid="chat-policy"
              aria-label={t("shell.sidebar.chat")}
            >
              {channelLocale}
            </span>
            <div data-testid="chat-tags">
              {visibleTags.map((tag, index) => (
                <span key={`${tag}-${index}`} data-testid={`chat-tag-${index}`}>
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        {pendingAsk !== null ? (
          <div
            data-testid="permission-dialog"
            role="dialog"
            aria-label={pt("chat.permission.title", "Install permission")}
          >
            <p>
              {pt(
                "chat.permission.body",
                "The run needs install permission for '{tool}'.",
                { tool: pendingAsk.toolName },
              )}
            </p>
            <p data-testid="permission-tool">{pendingAsk.toolName}</p>
            <button
              type="button"
              data-testid="permission-allow"
              onClick={() => {
                answerAsk(true);
              }}
            >
              {pt("chat.permission.allow", "Allow")}
            </button>
            <button
              type="button"
              data-testid="permission-deny"
              onClick={() => {
                answerAsk(false);
              }}
            >
              {pt("chat.permission.deny", "Deny")}
            </button>
          </div>
        ) : null}
        {/* FXDESIGN6: one rounded box docked at the bottom: the field
            inside, the send as an icon button inside right; a small status
            line under it (model | route | working state). */}
        <div data-testid="chat-composer" className="fx-composer">
          {draft !== "" ? (
            <span data-testid="chat-draft-chip" className="fx-quiet">{t("chat.composer.draft")}</span>
          ) : null}
          {boundModels !== null && boundModels.length === 0 ? (
            <div className="fx-composer-hint">
              <p data-testid="chat-no-model-hint" className="fx-quiet">{t("chat.composer.noModel")}</p>
              <a data-testid="chat-no-model-connect" href="/settings/models" className="fx-btn-quiet">
                {t("chat.hierarchy.connect")}
              </a>
            </div>
          ) : null}
          <div className="fx-composer-box">
            <label className="fx-composer-field">
              <span className="fx-vh">{t("chat.composer.prompt")}</span>
              <input
                data-testid="chat-prompt"
                type="text"
                placeholder={t("chat.composer.prompt")}
                aria-label={t("chat.composer.prompt")}
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    handleSend();
                  }
                }}
              />
            </label>
            <button
              type="button"
              data-testid="chat-send"
              className="fx-send-btn"
              aria-label={t("chat.composer.send")}
              title={t("chat.composer.send")}
              disabled={draft.trim() === "" || streaming}
              onClick={handleSend}
            >
              <Icon name="send" />
              <span className="fx-vh">{t("chat.composer.send")}</span>
            </button>
          </div>
          <p data-testid="chat-statusline" className="fx-statusline">            {/* FXDESIGN6: one span per value; the "|" dividers are CSS
                (no separator text nodes, so the locale-only contract
                sees exactly the three locale values). */}
            <span>{directorModel ?? t("chat.hierarchy.auto")}</span>
            <span>{statusRoute()}</span>
            <span>
              {streaming
                ? t("chat.composer.statusWorking")
                : t("chat.composer.statusReady")}
            </span>
          </p>
          {streaming && draft.trim() !== "" ? (
            <span data-testid="chat-wait-line" role="status" className="fx-quiet">
              {pt(
                "chat.stream.wait",
                "Wait for this to finish or press Stop",
              )}
            </span>
          ) : null}
          {streaming ? (
            <span data-testid="chat-spinner" role="status" className="fx-quiet">
              {t("chat.stream.spinner")}
            </span>
          ) : null}
          {streaming ? (
            <button
              type="button"
              data-testid="chat-abort"
              className="fx-btn-quiet"
              onClick={handleAbort}
            >
              {t("chat.abort.cancel")}
            </button>
          ) : null}
          {online ? null : (
            <span data-testid="chat-offline-dot" role="status" className="fx-quiet">
              {t("chat.stream.offline")}
            </span>
          )}
          {health === "degraded" ? (
            <span data-testid="chat-health-degraded" role="status" className="fx-quiet">
              {t("errors.generic")}
            </span>
          ) : null}
          {health === "reconnecting" ? (
            <span data-testid="chat-health-reconnecting" role="status" className="fx-quiet">
              {t("chat.stream.offline")}
            </span>
          ) : null}
        </div>
        {flooded ? (
          <div data-testid="chat-flood-warning" role="alert">
            <p>{t("api.error.delta_over_bound")}</p>
            <button
              type="button"
              data-testid="chat-compact-resend"
              disabled={streaming}
              onClick={handleCompactResend}
            >
              {t("ui.error.retry")}
            </button>
          </div>
        ) : null}
        {blocking !== null ? (
          <ErrorPanel
            errorKey={blocking.errorKey}
            code={blocking.code}
            onRetry={handleRetry}
          />
        ) : null}
        {toast !== null ? (
          <div data-testid="chat-toast" role="status">
            {toast}
          </div>
        ) : null}
      </div>
    </section>
  );
}
