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
import { readLedgerWithRuns } from "../api/projectsApi";
import { DEFAULT_LOCALE, formatScreenTime, t } from "../locale/index";
import enTable from "../locale/en.json";
import { ApprovalCard } from "./ApprovalCard";
import { HierarchyRows } from "./HierarchyRows";
import {
  appendChatMessage,
  dequeueChatPrompt,
  enqueueChatPrompt,
  getChatDraft,
  getChatState,
  patchChatMessage,
  prependChatMessages,
  setChatDraft,
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
import {
  getPreset,
  getProviderCatalog,
} from "../settings/ProvidersPage/catalog";
import { readRoleProfiles } from "../settings/index";
import { readTeamMode, saveTeamMode } from "../settings/projectLimitsApi";
import { Icon } from "../ui/icons";
import { Spinner } from "../ui/Spinner";
import {
  askPermission,
  installDisplayCommand,
  isInstallPermissionAsk,
  pt,
  readInstallArgv,
  recordProjectGrant,
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
  /** Failed task text for the one-line error ("which step"), if known. */
  task?: string;
  /** FXSTORE: routed provider id on secret-store terminals (ids only). */
  providerId?: string;
  /** R8(b): provider display label for a no-model stop. */
  provider?: string;
}

/** FXSTORE: product label for a provider id (locale-independent names:
 * "Meta" reads the same in en and uk). Unknown ids pass through, so
 * the line never hides which key is missing. */
function providerLabel(providerId: string | undefined): string {
  const id = (providerId ?? "").trim();
  if (id === "") {
    return "provider";
  }
  try {
    const found = getPreset(getProviderCatalog(), id);
    if (found !== undefined) {
      return found.label;
    }
  } catch {
    // Catalog unreadable: the raw id still names the key.
  }
  return id;
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
  // FXASK A8: a parked install ask arrived on this open stream (the run
  // waits in place). Answering records the decision only, never resends;
  // the flag clears on answer or when the stream ends.
  askOpen: boolean;
}

const pumps = new Map<string, ChatPump>();

// FXSAVED item 5: live-pump signal for the close warning. True while any
// chat pump drives a stream; the shell ClosingGuard arms on it through
// useSyncExternalStore, so closing the window mid-run warns while an
// idle app closes quietly.
const pumpListeners = new Set<() => void>();
let pumpVersion = 0;

function emitPumpsChanged(): void {
  pumpVersion += 1;
  for (const notify of [...pumpListeners]) {
    notify();
  }
}

export function subscribeLivePumps(listener: () => void): () => void {
  pumpListeners.add(listener);
  return () => {
    pumpListeners.delete(listener);
  };
}

/** True while any chat pump drives a stream (test and guard probe). */
export function hasLivePump(): boolean {
  return pumps.size > 0;
}

export function useLivePumpActive(): boolean {
  return useSyncExternalStore(
    subscribeLivePumps,
    () => pumps.size > 0,
    () => pumps.size > 0,
  );
}

// A card shows ONLY for a live waiting proposal: the stream's own
// clean terminal event marks the message id here. Default is no card —
// history, failed, stopped, engine and interrupted turns never mark,
// so a restart or a remount can never resurrect one. The store shape
// is frozen, so the per-message mark lives here, keyed by the unique
// store message id.
const proposalMessages = new Set<string>();

// Engine turns (done event with executed:true, or a served turn with
// the executed mark) render a verdict line plus the disclosed steps,
// never the approval card. The map carries the terminal state per
// message id; history never marks a proposal. The store shape is
// frozen, so the per-message mark lives here, keyed by the unique
// store message id.
const engineTurnStatus = new Map<string, "ok" | "failed" | "stopped">();

// FXWHERE: run id per assistant message id, so the verdict can name the
// project folder from the runs ledger (run_id -> folder). Live runs set
// it at creation; served history turns carry their stored run_id.
const engineTurnRun = new Map<string, string>();

// Stopped-turn assistants show one plain stopped line instead of the card.
const stoppedAssistants = new Set<string>();

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

// FXCHATV V3: the pending ask is keyed by PROJECT, not by slice.
// A slice key changes mid-run (client swap, project switch, remount),
// so a slice-keyed ask parks where no mounted UI ever reads it: the
// rail says Blocked while no card is reachable. The project-keyed ask
// reaches any mounted ChatArea of the same project, survives restart
// through a stable per-project mirror, and the mount consumes it.
const askByProject = new Map<string, InstallPermissionAsk>();
const projectAskListeners = new Map<string, Set<() => void>>();

const sliceProjectId = new Map<string, string>();

function projectMirrorKey(projectId: string): string {
  return `fxchat.ask.p.${projectId}`;
}

function writeProjectMirror(
  projectId: string,
  ask: InstallPermissionAsk | null,
): void {
  try {
    if (ask === null) {
      window.sessionStorage.removeItem(projectMirrorKey(projectId));
      return;
    }
    window.sessionStorage.setItem(
      projectMirrorKey(projectId),
      JSON.stringify({ toolName: ask.toolName, messageId: ask.messageId }),
    );
  } catch {
    return;
  }
}

function readProjectMirror(projectId: string): InstallPermissionAsk | null {
  try {
    const raw = window.sessionStorage.getItem(projectMirrorKey(projectId));
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

export function subscribeProjectAsk(
  projectId: string,
  listener: () => void,
): () => void {
  let watchers = projectAskListeners.get(projectId);
  if (watchers === undefined) {
    watchers = new Set();
    projectAskListeners.set(projectId, watchers);
  }
  watchers.add(listener);
  return () => {
    const live = projectAskListeners.get(projectId);
    if (live !== undefined) {
      live.delete(listener);
      if (live.size === 0) {
        projectAskListeners.delete(projectId);
      }
    }
  };
}

function emitProjectAsk(projectId: string): void {
  const watchers = projectAskListeners.get(projectId);
  if (watchers === undefined) {
    return;
  }
  for (const notify of [...watchers]) {
    notify();
  }
}

export function readProjectAsk(projectId: string): InstallPermissionAsk | null {
  return askByProject.get(projectId) ?? null;
}

function stashProjectAsk(projectId: string, ask: InstallPermissionAsk): void {
  askByProject.set(projectId, ask);
  writeProjectMirror(projectId, ask);
  emitProjectAsk(projectId);
}

function consumeProjectAsk(projectId: string): InstallPermissionAsk | null {
  const stashed = askByProject.get(projectId);
  if (stashed !== undefined) {
    askByProject.delete(projectId);
    return stashed;
  }
  return readProjectMirror(projectId);
}

/** Assistants whose runs really ended (done, failed or stopped — never
a hold, which ends the stream but leaves the answer pending). A parked
card for one of them never restores: the card closes when its run ends
(FXASK A7). Precedent: deadAssistants/stoppedAssistants below. */
const endedAssistants = new Set<string>();

export function markAssistantRunEnded(id: string): void {
  endedAssistants.add(id);
}

export function isAssistantRunEnded(id: string): boolean {
  return endedAssistants.has(id);
}

/** Close the project card when it belongs to the ended run. Only an
exact bubble match closes: a live hold for another run never loses its
card because this run ended. */
function closeAskForEndedRun(projectId: string, assistantId: string): void {
  const stashed = readProjectAsk(projectId);
  if (stashed !== null && stashed.messageId === assistantId) {
    clearProjectAsk(projectId);
  }
}

function clearProjectAsk(projectId: string): void {
  askByProject.delete(projectId);
  writeProjectMirror(projectId, null);
}

/** Park without notifying (unmount path): the next mount consumes it. */
function parkProjectAsk(projectId: string, ask: InstallPermissionAsk): void {
  askByProject.set(projectId, ask);
  writeProjectMirror(projectId, ask);
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
  // FXCHATV V3: project-keyed delivery. A slice-keyed ask parks where
  // no mounted UI ever reads it when the slice key changed mid-run, so
  // the live ask goes to the project: any mounted ChatArea of the same
  // project shows the card, otherwise the mount consumes the stash.
  const projectId = sliceProjectId.get(key);
  if (projectId !== undefined) {
    const ui = sliceUI.get(key);
    if (ui !== undefined) {
      ui.onAsk(ask);
    }
    stashProjectAsk(projectId, ask);
    return;
  }
  const ui = sliceUI.get(key);
  if (ui !== undefined) {
    ui.onAsk(ask);
    return;
  }
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
  executed: z.boolean().optional().default(false),
  run_end_reason: z.string().optional().default(""),
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

/** Named disconnect line: the run stopped when the window closed. */
function disconnectClosedText(): string {
  return pt(
    "chat.stream.disconnectClosed",
    "The run stopped when the window closed. Files so far are kept. Send the task again.",
  );
}

/** FXOPEN J6: visible composer rows for a draft, about six lines max.
Newlines always count (pasted tasks grow at once); the measured pixel
height covers wrapped lines in a real browser. jsdom reports no
layout, so the text count alone drives the rows there. */
export const COMPOSER_MAX_ROWS = 6;

export function composerRowsFor(
  text: string,
  lineHeightPx: number,
  scrollHeightPx: number,
): number {
  const line = lineHeightPx > 0 ? lineHeightPx : 20;
  const fromText = text.split("\n").length;
  const fromMeasure = Math.ceil(Math.max(0, scrollHeightPx) / line);
  return Math.min(
    COMPOSER_MAX_ROWS,
    Math.max(1, fromText, fromMeasure),
  );
}

/** FXCHATV V1: a run-log-looking text renders as one plain verdict line
plus a collapsed Details disclosure, never twice. Markers are the
engine's own vocabulary (Working folder, Team, Director, Part, Check,
Total, run success/fail, cost lines): a juror reads the verdict, the
full log stays behind Details. Plain answers keep the verdict card. */
/** R05: plain (non-engine-looking) output has no engine structure to
summarise, so its verdict view opens on the assistant message text:
the return-to-chat rows read the text itself, never a bare verdict. */
const ENGINE_LOG_MARKERS =
  /^(?:working folder|team|director|part\s+\S+|check\s+\S+|total|run (?:success|fail)|.*cost:)/im;

export function looksLikeEngineLog(text: string): boolean {
  return ENGINE_LOG_MARKERS.test(text);
}

/** FXCHATV (d): check lines name the program only, never a full
machine path (C:\Windows\..., C:\tool\...); a user profile segment
(C:\Users\<name>) never reaches the screen. The working-folder line
itself is untouched: it lives only inside Details.
FXOPEN O4: any other absolute Windows path token shows its file name
only (no drive, no user name) — the backstop for history rows stored
before the server started sending relative paths. */
export function shortProgramLine(line: string): string {
  const redacted = line.replace(/C:\\Users\\[^\\\s"']+/gi, "~");
  const where = VERDICT_WHERE_RE.exec(redacted);
  const body = where !== null ? redacted.slice(0, where.index) : redacted;
  const shortCmd = body.replace(
    /(\$\s+)([A-Za-z]:[\\/][^\s"']+)/g,
    (_match, head: string, token: string) => {
      const base = token.split(/[\\/]/).pop() ?? token;
      const name = base.replace(/\.(exe|cmd|bat|ps1)$/i, "").toLowerCase();
      return `${head}${name}`;
    },
  );
  const shortBody = shortCmd.replace(/[A-Za-z]:[\\/][^\s"']*/g, (token: string) => {
    const base = token.split(/[\\/]/).pop() ?? token;
    return base !== "" ? base : token;
  });
  if (where === null) {
    return shortBody;
  }
  return (
    shortBody + `, in ${where[1] ?? ""}` + redacted.slice(where.index + where[0].length)
  );
}

/** FXCHATV V4: one live step line while a run works — the current
part, the count of check/step rows so far, the last streamed row in
plain words, and elapsed seconds. Data comes from the streamed
deltas only (the live store text); no raw machine paths. */
export function liveStepLine(
  text: string,
  startedAt: number,
  nowMs: number,
): string {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  const elapsed = Math.max(0, Math.floor((nowMs - startedAt) / 1000));
  let part: string | null = null;
  let steps = 0;
  for (const line of lines) {
    const found = /Part\s+([A-Za-z0-9_-]+)/.exec(line);
    if (found !== null && found[1] !== undefined) {
      part = found[1];
    }
    if (/^(Check|Step)\b/i.test(line)) {
      steps += 1;
    }
  }
  const lastRaw = lines[lines.length - 1] ?? "";
  const last = shortProgramLine(lastRaw).slice(0, 90);
  const who = part === null ? "Worker" : `Worker ${part}`;
  const doing = last !== "" ? last : "waiting for the model";
  return `${who}, step ${steps}, ${doing}, ${elapsed} s`;
}

/** FXCHATV V5: the plain layer carries no raw words. cost UNKNOWN
becomes cost not known; a run-success line becomes the final line. */
export function costKnown(text: string): boolean {
  return !/cost:\s*unknown/i.test(text);
}

/** FXR3B: engine-turn verdict from the lines plus the terminal state.
No new server events: the text carries the part rows ("Part p1:
PASS"), "[files: ...]" markers and run lines; the done event (or the
served executed flag) says it is an engine turn, the terminal state
says Done vs Failed. Every original line is kept verbatim for the
steps disclosure below the verdict.
*/
export interface EngineSummary {
  done: boolean;
  parts: number;
  passed: number;
  files: string[];
  lines: string[];
  /** FXASK A7: install-hold command (`Waiting for your permission to
  run <command>.`), null when the text holds no run-held line. A held
  run is never Done, never a 0-parts line. */
  held: string | null;
  /** FXASK A3: denied install command (`Install permission denied
  for <command>`), null when no deny line. A denied run never says
  Done. */
  denied: string | null;
  /** FXOPEN O4: one plain line when the text announces a second plan
  ("Director: plan of 2 parts" then "of 3 parts"); null otherwise. */
  planChanged: string | null;
  /** FXANSWER: the plain answer text when the run ended as an answer
  (server marker below); null when the run answered nothing. */
  answer: string | null;
  /** FXANSWERb-1: the run is a team-off solo run (its own "Done, not
  audited." line); solo runs have no Part rows, so the verdict reads
  the solo line plus the real files instead of the empty-plan line. */
  solo: boolean;
  /** FXWHERE: the project folder the files went into (resolved from
  the runs ledger by run id); null when unknown, then the verdict
  keeps the pre-FXWHERE shape. */
  folder: string | null;
  /** R8(b): the served stop reason when the run ended before any
  model call ("no-provider" | "no-model"), else null. The verdict
  reads this reason as the main line, never the no-parts sentence. */
  stopReason: "no-provider" | "no-model" | null;
  /** R8(b): provider display label for a no-model stop. */
  stopProvider: string | null;
}

const PLAN_OF_RE = /Director:\s*plan of (\d+)\s*parts?/i;

/** FXOPEN O4: a re-planned run says so in one plain line, never by
silently growing "of 2 parts" into "of 3 parts". The reason names the
old and the new part count; null when the text holds at most one
plan announcement. */
export function planChangedLine(text: string): string | null {
  const counts: number[] = [];
  for (const line of text.split("\n")) {
    const found = PLAN_OF_RE.exec(line);
    if (found?.[1] === undefined) {
      continue;
    }
    const count = Number(found[1]);
    if (!counts.includes(count)) {
      counts.push(count);
    }
  }
  if (counts.length < 2) {
    return null;
  }
  const first = counts[0] ?? 0;
  const last = counts[counts.length - 1] ?? 0;
  const word = (n: number): string => (n === 1 ? "part" : "parts");
  return (
    `Plan changed: the director announced a new plan ` +
    `(was ${first} ${word(first)}, now ${last} ${word(last)})`
  );
}

/** FXANSWER: the server marker for a run that ended as a plain answer
(no parts, no build). The visible reply is the answer text itself. */
export const PLAIN_ANSWER_MARKER = "run answered: plain answer, no parts";

/** FXANSWER: the answer text of a plain-answer run: the run text minus
engine-log lines and the marker itself. Null when the run answered
nothing. A marker with no extractable answer falls back to the text
minus the marker only, so an answer never reads as "Nothing was built". */
export function extractPlainAnswer(text: string): string | null {
  if (!text.includes(PLAIN_ANSWER_MARKER)) {
    return null;
  }
  const lines = text.split("\n").map((line) => line.trim());
  const stripped = lines.filter(
    (line) =>
      line !== "" &&
      line !== PLAIN_ANSWER_MARKER &&
      !line.startsWith("[files:") &&
      !ENGINE_LOG_MARKERS.test(line),
  );
  const kept = stripped.length > 0
    ? stripped
    : lines.filter(
      (line) => line !== "" && line !== PLAIN_ANSWER_MARKER,
    );
  if (kept.length === 0) {
    return null;
  }
  return kept.join("\n");
}

export function summarizeEngineTurn(
  text: string,
  status: "ok" | "failed" | "stopped",
  folder: string | null = null,
): EngineSummary {
  const lines = text.split("\n");
  const verdicts = new Map<string, boolean>();
  const files: string[] = [];
  // FXASK A7: a run-held line names the waiting command. A held
  // run is never Done, never a 0-parts line: the verdict is the
  // Waiting sentence, from the engine's own words.
  let held: string | null = null;
  // FXASK A3: a denied install line closes the turn failed. A denied
  // run never says Done, even with files listed and zero part rows.
  let denied: string | null = null;
  for (const line of lines) {
    if (held === null) {
      const waiting =
        /waiting for your permission to run\s+([^\n]+?)\s*\.?\s*$/i.exec(
          line,
        );
      if (waiting?.[1] !== undefined) {
        const command = waiting[1].trim().replace(/\s*\.\s*$/, "");
        held = command !== "" ? command : null;
      }
    }
    if (denied === null) {
      const refused = /install permission denied for\s+([^\n]+)/i.exec(
        line,
      );
      if (refused?.[1] !== undefined) {
        const words = refused[1].trim().split(/\s+/).slice(0, 2);
        const command = words.join(" ");
        denied = command !== "" ? command : null;
      }
    }
    const part = /^Part\s+([^:]+):\s*(PASS|FAIL)\b/i.exec(line);
    if (part !== null && part[1] !== undefined && part[2] !== undefined) {
      verdicts.set(part[1].trim(), part[2].toUpperCase() === "PASS");
    }
    // PLANB V2f: a part whose files do not exist yet is announced as
    // "(planned: a, b)" (L5); those names count as the run's files too.
    const planned = /^Part\s+[^:]+:.*\(planned:\s*([^)]+)\)/i.exec(line);
    for (const filesMatch of [
      ...line.matchAll(/\[files:\s*([^\]]+)\]/gi),
      ...(planned === null ? [] : [planned]),
    ]) {
      const listed = filesMatch[1];
      if (listed === undefined) {
        continue;
      }
      for (const name of listed.split(",")) {
        const file = name.trim();
        if (file !== "" && !files.includes(file)) {
          files.push(file);
        }
      }
    }
  }
  const parts = verdicts.size;
  let passed = 0;
  for (const ok of verdicts.values()) {
    if (ok) {
      passed += 1;
    }
  }
  // FXZERO R1: a run with zero "Part ...: PASS/FAIL" rows is hollow
  // unless the run's own lines evidence work: its success count line
  // ("run success: all N parts PASS"), its announced plan
  // ("Director: plan of N parts"), or the team-off solo marker
  // ("Done, not audited."). A hollow run never says Done.
  // FXANSWER: a plain-answer run (server marker) is never hollow: it
  // answered with no parts, and its visible reply is the answer text.
  const plainAnswer = extractPlainAnswer(text);
  const soloDone = /Done, not audited\./.test(text);
  let wholeParts = parts;
  let wholePassed = passed;
  if (wholeParts === 0 && !soloDone) {
    const runOk = /run success:\s*all (\d+)\s+parts?\s+PASS/i.exec(text);
    if (runOk?.[1] !== undefined) {
      wholeParts = Number.parseInt(runOk[1], 10);
      wholePassed = wholeParts;
    } else {
      const plans = [...text.matchAll(
        /Director:\s*plan of (\d+)\s+parts?/gi)];
      const lastPlan = plans.length === 0
        ? 0
        : Number.parseInt(
            plans[plans.length - 1]?.[1] ?? "0",
            10,
          );
      if (Number.isFinite(lastPlan) && lastPlan > 0) {
        wholeParts = lastPlan;
      }
    }
  }
  // FXASK A3 + FXANSWER: model text is not evidence. Zero part rows
  // with no engine evidence (success count, announced plan, solo
  // marker, plain answer) is hollow even when the text lists files:
  // files alone never say Done, and a 0-part run with no answer never
  // says Done.
  const hollow =
    wholeParts === 0 && !soloDone && plainAnswer === null;
  const failed =
    status !== "ok" ||
    hollow ||
    held !== null ||
    denied !== null ||
    (wholeParts > 0 ? wholePassed < wholeParts : /run fail/i.test(text));
  // R8(b): a run stopped before any model call carries its reason as
  // the main line (served words), never the no-parts sentence.
  let stopReason: EngineSummary["stopReason"] = null;
  let stopProvider: string | null = null;
  if (text.includes(NO_PROVIDER_LINE)) {
    stopReason = "no-provider";
  } else {
    const noModel = NO_MODEL_RE.exec(text);
    if (noModel !== null && noModel[1] !== undefined) {
      stopReason = "no-model";
      stopProvider = noModel[1].trim();
    }
  }
  return {
    done: !failed,
    parts: wholeParts,
    passed: wholePassed,
    files,
    lines,
    held,
    denied,
    planChanged: planChangedLine(text),
    answer: plainAnswer,
    folder,
    solo: soloDone,
    stopReason,
    stopProvider,
  };
}

/** FXWHERE: the folder segment of the verdict. A user profile segment
(C:\Users\<name>) never reaches the screen; the real project folder
does, so the verdict says WHERE the files went. */
export function verdictFolderLabel(folder: string): string {
  return folder.replace(/C:\\Users\\[^\\\s"']+/gi, "~");
}

/** FXWHERE: a verdict `, in <folder>` tail keeps its real path (the
user profile segment is already ~ above); it is not an executable
token, so the drive-letter strip below must not basename it. */
const VERDICT_WHERE_RE = /, in ((?:[A-Za-z]:[\\/]|~[\\/])[^\s"']*)/;

/** R8(b): served stop reasons for a run that ended before any
model call. These literals are the engine's stable summary words;
the verdict matches them and renders the localized main line. */
export const NO_PROVIDER_LINE = "Connect a provider first";
export const NO_MODEL_RE = /^(.*) has no model chosen$/m;

/** FXZERO R1 plain sentence for a zero-part run: nothing was built,
the plan had no parts, what to say next plus one example. Localised
en + uk; never Done, never a raw id. */
function emptyPlanLine(costNote = ""): string {  const example = pt(
    "chat.run.emptyPlanExample",
    "Add a contact page with a test.",
  );
  const sentence = pt(
    "chat.run.emptyPlan",
    "Nothing was built — the plan had no parts. Say what you want built, for example: “{example}”",
    { example },
  );
  return `${sentence}${costNote}.`;
}

/** One plain verdict line for a finished engine turn. FXANSWER: a
plain-answer run reads as the answer text itself, never Done/Failed,
never the nothing-built sentence. */
export function engineVerdictLine(
  summary: EngineSummary,
  costNote = "",
): string {
  // FXDENYLINE: a denied run reads its REAL end state (Stopped), never a
  // stale Waiting line: the deny epilogue lands on text that still holds
  // the earlier hold line, so denied wins over held.
  // FXASK A3: a denied install closes Stopped with what was refused
  // and why (nothing was installed), never Done, never 0-parts.
  if (summary.denied !== null) {
    return pt(
      "chat.permission.deniedRun",
      "Stopped: you denied {command}. Nothing was installed.",
      { command: summary.denied },
    );
  }
  // FXASK A7: a held run waits, never Done, never a 0-parts line.
  if (summary.held !== null) {
    return pt(
      "chat.permission.waitingHold",
      "Waiting for your permission to run {command}.",
      { command: summary.held },
    );
  }
  // R8(b): a run stopped before any model call reads its reason as
  // the main line (localized, en + uk), never the no-parts sentence.
  if (summary.stopReason === "no-provider") {
    return pt("chat.run.noProviderLine", "Connect a provider first");
  }
  if (summary.stopReason === "no-model") {
    return pt(
      "chat.run.noModelLine",
      "{provider} has no model chosen",
      { provider: summary.stopProvider ?? "provider" },
    );
  }
  if (summary.answer !== null && summary.answer !== "") {
    return summary.answer;
  }
  if (summary.solo) {
    // FXANSWERb-1: a solo run has no Part rows: the verdict reads the
    // solo line plus the real files, never the empty-plan line while
    // the files are on disk. A solo run that wrote nothing and
    // answered nothing stays not Done.
    const where =
      summary.folder !== null && summary.folder !== ""
        ? `, in ${verdictFolderLabel(summary.folder)}`
        : "";
    if (summary.done) {
      const files =
        summary.files.length > 0
          ? `, files: ${summary.files.join(", ")}`
          : "";
      return `Done, not audited${files}${where}${costNote}.`;
    }
    if (summary.files.length === 0) {
      return emptyPlanLine(costNote);
    }
    return `Failed — 0 parts, 0 passed, files: ${summary.files.join(", ")}${where}${costNote}.`;
  }
  if (summary.parts === 0) {
    return emptyPlanLine(costNote);
  }
  const head = summary.done ? "Done" : "Failed";
  const parts =
    summary.parts === 1
      ? "1 part"
      : `${summary.parts} parts`;
  const passed =
    summary.passed === 1 ? "1 passed" : `${summary.passed} passed`;
  const files =
    summary.files.length > 0
      ? `files: ${summary.files.join(", ")}` +
        (summary.folder !== null && summary.folder !== ""
          ? `, in ${verdictFolderLabel(summary.folder)}`
          : "")
      : "files: none listed";
  const next = summary.done
    ? ""
    : " Next: fix the failing part, then send the task again.";
  return `${head} — ${parts}, ${passed}, ${files}${costNote}.${next}`;
}

/** FXR3B: finished engine turn — verdict line first, steps disclosed. */
/** FXCHATV V1: the verdict is the one plain reply line; the run log
lives once, behind a collapsed Details disclosure (V5: plain layer
carries no raw words, so the cost line becomes cost not known; (d):
check lines name the program only). */
export function EngineTurnView(props: {
  text: string;
  status: "ok" | "failed" | "stopped";
  /** FXWHERE: project folder the files went into (runs ledger, keyed
  by run id). Null/omitted keeps the pre-FXWHERE verdict line. */
  folder?: string | null;
}): ReactElement {
  const summary = summarizeEngineTurn(
    props.text,
    props.status,
    props.folder ?? null,
  );
  const costNote = costKnown(props.text) ? "" : ", cost not known";
  // FXANSWER item 4: a stopped run says Stopped, never Failed, never a
  // parts verdict. The Details disclosure below stays as it is.
  const stoppedLine = pt("chat.run.stopped", "Stopped.");
  // FXDENYLINE: a stopped run that was denied keeps the real reason
  // (what was refused), not the bare Stopped line.
  const verdict =
    props.status === "stopped" && summary.denied === null
      ? stoppedLine
      : engineVerdictLine(summary, costNote);
  // R05: the disclosure collapses only recognised engine logs. Plain
  // output (no engine markers) opens on the assistant message text, so
  // live and return-to-chat rows render the identical visible text.
  const [open, setOpen] = useState(
    !summary.done || !looksLikeEngineLog(props.text),
  );
  return (
    <>
      <p data-testid="run-verdict" style={{ whiteSpace: "pre-wrap" }}>
        {shortProgramLine(verdict)}
      </p>
      {/* R8(b): a stop before any model call links the fix next to
          the reason (never hidden behind Details). */}
      {props.status !== "stopped" && summary.stopReason !== null ? (
        <a data-testid="run-verdict-connect" href="/settings/models">
          {t("chat.hierarchy.connect")}
        </a>
      ) : null}
      {summary.planChanged !== null ? (
        <>
          {" "}
          <p data-testid="plan-changed" style={{ whiteSpace: "pre-wrap" }}>
            {summary.planChanged}
          </p>
        </>
      ) : null}{" "}
      <button
        type="button"
        data-testid="run-steps-toggle"
        className="fx-btn-quiet"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
      >
        {pt("chat.run.steps", "Details")}
      </button>{" "}
      <div data-testid="run-steps" hidden={!open}>
        {summary.lines.map((line, index) => (
          <p key={`${index}`} style={{ whiteSpace: "pre-wrap" }}>
            {index > 0 ? " " : null}
            {shortProgramLine(line)}
          </p>
        ))}
      </div>
    </>
  );
}

// FXWHERE: run id -> project folder from the runs ledger; unknown
// keeps the pre-FXWHERE verdict line (null folder).
function folderForMessage(
  messageId: string,
  runFolders: Record<string, string>,
): string | null {
  const runId = engineTurnRun.get(messageId);
  if (runId === undefined) {
    return null;
  }
  return runFolders[runId] ?? null;
}

// Merge one served page into the slice, oldest first. Merge key is the
// server turn id only: identical user texts ("hello" twice) never drop
// nor duplicate. A running turn whose stream is gone renders as
// interrupted with its stored text plus a resend — or the named
// disconnect line when the server record says the window closed;
// failed and stopped turns restore the error card.
// FXOPEN O4: one entry per interrupted task — after a restart the same
// task can stand twice (10:11 + 10:14, each with Resend); running
// turns sharing one user text collapse to the latest, everything else
// keeps its row.
function buildHistoryBatch(
  key: string,
  page: ChatHistoryPage,
): { batch: NewChatMessage[]; sawTerminal: boolean } {
  const lastInterruptedByTask = new Map<string, number>();
  page.turns.forEach((turn, index) => {
    if (turn.status === "running" && turn.user_text.trim() !== "") {
      lastInterruptedByTask.set(turn.user_text.trim(), index);
    }
  });
  const turns = page.turns.filter((turn, index) => {
    if (turn.status !== "running" || turn.user_text.trim() === "") {
      return true;
    }
    return lastInterruptedByTask.get(turn.user_text.trim()) === index;
  });
  const known = new Set(
    getChatState(key).messages.map((message) => message.id),
  );
  const batch: NewChatMessage[] = [];
  let sawTerminal = false;
  for (const turn of turns) {
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
    if (turn.status === "interrupted") {
      // FXANSWER item 4: only a restart-reconciled row carries the
      // app-closed banner. Same shape as a leftover running row used
      // to render: stored text plus a resend, never a card.
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
    if (turn.status === "running") {
      batch.push({
        id: userId,
        role: "user",
        text: turn.user_text,
        at,
        final: true,
      });
      const closedByWindow =
        typeof turn.run_end_reason === "string" &&
        turn.run_end_reason.includes("client disconnect");
      // FXANSWER item 4: a running row the startup reconcile did not
      // mark is still live (or its terminal write is still in flight):
      // no app-closed banner, no error card. Only a recorded client
      // disconnect names the window-closed line.
      batch.push({
        id: assistantId,
        role: "assistant",
        text: closedByWindow
          ? `${turn.assistant_text !== "" ? `${turn.assistant_text}\n` : ""}${disconnectClosedText()}`
          : turn.assistant_text,
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
    if (turn.run_id !== "") {
      // FXWHERE: served run id rides to the verdict folder lookup.
      engineTurnRun.set(assistantId, turn.run_id);
    }
    if (turn.assistant_text !== "") {
      batch.push({
        id: assistantId,
        role: "assistant",
        text: turn.assistant_text,
        at,
        final: true,
      });
      if (turn.executed === true) {
        // Served engine mark: the verdict view renders from the lines,
        // never the approval card. Status rides along for Done/Failed.
        engineTurnStatus.set(
          assistantId,
          turn.status === "stopped"
            ? "stopped"
            : turn.status === "failed"
              ? "failed"
              : "ok",
        );
      } else if (looksLikeEngineLog(turn.assistant_text)) {
        // FXCHATV V1: a served run log without the executed flag is an
        // engine reply too: verdict plus Details, never the card.
        // History never marks a proposal: default is no card.
        engineTurnStatus.set(
          assistantId,
          turn.status === "stopped"
            ? "stopped"
            : turn.status === "failed"
              ? "failed"
              : "ok",
        );
      }
      if (turn.status === "stopped") {
        // Stopped turns show one plain stopped line instead of a card.
        // History never marks a proposal: default is no card.
        stoppedAssistants.add(assistantId);
      }
    }
    if (turn.status === "failed") {
      // FXANSWER item 4: a stopped run is not an error: no error card,
      // no degraded health, no Retry. Failed turns keep the card.
      sawTerminal = true;
      const code = turn.error_code !== "" ? turn.error_code : "UNKNOWN";
      // R8(b): a no-model stop keeps its provider for the banner line.
      const noModel =
        code === "PROVIDER_NO_MODEL"
          ? NO_MODEL_RE.exec(turn.assistant_text ?? "")
          : null;
      emitBlocking(key, {
        errorKey: apiErrorLocaleKey(code),
        code,
        task: turn.user_text,
        ...(noModel?.[1] === undefined
          ? {}
          : { provider: noModel[1].trim() }),
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

/** FXCOPY: quiet clipboard copy (Ctrl+C path untouched, no UI noise). */
function copyQuiet(text: string): void {
  try {
    const nav = navigator as Navigator & {
      clipboard?: { writeText(value: string): Promise<void> };
    };
    if (nav.clipboard !== undefined) {
      void nav.clipboard.writeText(text).catch(() => undefined);
      return;
    }
  } catch {
    return;
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
  } catch {
    return;
  }
}

/** FXCOPY: inline copy glyph (icon-only: no locale text node rendered). */
function CopyGlyph(): ReactElement {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
      focusable="false"
      className="fx-icon"
    >
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </svg>
  );
}

/** Bubble timestamps through the one screen-time helper (HH:mm today). */
function formatChatTime(at: number): string {
  return formatScreenTime(at);
}

// Best-effort turn persist (USER write). A failed POST never surfaces.
// The running write opens the run (upsert key: run id); the terminal
// write (ok / failed / stopped) closes the same turn server-side.
async function recordTurnBestEffort(
  projectId: string,
  userText: string,
  assistantText: string,
  extra?: {
    status?: string;
    run_id?: string;
    error_code?: string;
    executed?: boolean;
  },
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
        executed: extra?.executed ?? false,
      },
    });
  } catch {
    return;
  }
}

let streamSeq = 0;

/** FXR3B J5: one human error line — what failed, which step, next
action. The code never reaches the screen. The task rides on the
blocking error when the failing turn is known (history reload), else
the last sent prompt of this slice. */
/** FXR3B J5: one human error line — what failed, which step, next
action. The code never reaches the screen (it rides only the tooltip
for diagnostics). The no-model case names the exact next step. */
function chatErrorText(
  blocking: BlockingError,
  prompt: string | null,
): string {
  if (
    blocking.code === "NO_PROVIDER_BOUND" ||
    blocking.errorKey === "firstrun.steps.connectProvider"
  ) {
    return t("chat.error.noProvider");
  }
  // R8(b): a run stopped before any model call names its reason as
  // the main line (localized, en + uk), never a generic retry line.
  if (blocking.code === "PROVIDER_NO_MODEL") {
    return t("chat.run.noModelLine", {
      provider:
        blocking.provider !== undefined && blocking.provider !== ""
          ? blocking.provider
          : providerLabel(blocking.providerId),
    });
  }
  // FXSTORE: a gone key names the provider plainly (with a Settings
  // link next to Retry); an unreadable store says so, never a missing key.
  if (blocking.code === "SECRET_VALUE_MISSING") {
    return t("chat.error.keyMissing", {
      label: providerLabel(blocking.providerId),
    });
  }
  if (blocking.code === "CREDENTIAL_STORE_UNREADABLE") {
    return t("chat.error.storeUnreadable");
  }
  const raw = blocking.task ?? prompt ?? "";
  const step =
    raw.trim() !== "" ? ` — task "${raw.trim().slice(0, 140)}"` : "";
  const what = t(blocking.errorKey);
  return `${what}${step}. ${pt("chat.error.retryHint", "Retry sends it again.")}`;
}

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
  // FXASK A7: a non-hold error ends the run for real: mark it so a
  // parked card for this bubble never restores, and close its own card.
  markAssistantRunEnded(assistantId);
  closeAskForEndedRun(
    record?.projectId ?? sliceProjectId.get(key) ?? "",
    assistantId,
  );
  const current = getChatState(key).messages.find(
    (message) => message.id === assistantId,
  );
  const failedCode = runErrorCode(error);
  if (record !== undefined) {
    // Failed runs are stored too (holds are not terminal: Allow replays
    // the same run id, so the held running turn upserts into one turn).
    const partial = current?.text ?? "";
    void recordTurnBestEffort(record.projectId, record.prompt, partial, {
      status: "failed",
      run_id: record.runId,
      error_code: failedCode,
    });
    if (failedCode === "NO_PROVIDER_BOUND") {
      // No model bound: the draft text stays so the user can connect a
      // provider and send the same task again. The restore itself runs
      // in the component (see the blocking effect below): this module
      // function never touches component state.
    }
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
      ...(record === undefined ? {} : { task: record.prompt }),
      // FXSTORE: the routed provider id rides along so the banner
      // names the missing key instead of a generic line.
      ...(error.details?.providerId === undefined
        ? {}
        : { providerId: error.details.providerId }),
    });
  } else {
    emitBlocking(key, {
      errorKey: "errors.generic",
      code: "UNKNOWN",
      ...(record === undefined ? {} : { task: record.prompt }),
    });
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
  sliceProjectId.set(key, projectId);
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
  // FXWHERE: live run id rides to the verdict folder lookup.
  engineTurnRun.set(assistantId, runId);
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
        // FXASK A8: mid-stream install ask (the run waits in place).
        // Marks this open stream as ask-open and shows the card; the
        // stream itself keeps going.
        onAsk: (ask) => {
          const pump = pumps.get(key);
          if (pump !== undefined) {
            pump.askOpen = true;
          }
          emitAsk(key, { toolName: ask.toolName, messageId: assistantId });
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
    askOpen: false,
  });
  emitPumpsChanged();
  runner.done.then(
    ({ aborted, executed }) => {
      pumps.delete(key);
      emitPumpsChanged();
      setChatRunner(key, { streamId: null, streaming: false });
      // FXASK A7: the run really ended with no hold (a hold rejects
      // the stream, never resolves it): its own card, if any, closes.
      markAssistantRunEnded(assistantId);
      closeAskForEndedRun(projectId, assistantId);
      const answer =
        getChatState(key).messages.find(
          (message) => message.id === assistantId,
        )?.text ?? "";
      const ranEngine = executed === true;
      if (aborted) {
        // Stop closes the run as stopped: stored, never Working. No
        // card mark: a stopped turn is never a waiting proposal.
        patchChatMessage(key, assistantId, { final: false });
        stoppedAssistants.add(assistantId);
        if (ranEngine) {
          engineTurnStatus.set(assistantId, "stopped");
        }
        void recordTurnBestEffort(projectId, text, answer, {
          status: "stopped",
          run_id: runId,
          error_code: "STOPPED",
          executed: ranEngine,
        });
      } else if (answer === "") {
        // Dropped stream (no terminal text): a clear failed line.
        patchChatMessage(key, assistantId, { final: false });
        setChatHealth(key, "degraded");
        void recordTurnBestEffort(projectId, text, answer, {
          status: "failed",
          run_id: runId,
          error_code: "EMPTY_RESPONSE",
          executed: ranEngine,
        });
        emitBlocking(key, {
          errorKey: apiErrorLocaleKey("UNKNOWN"),
          code: "UNKNOWN",
          task: text,
        });
      } else {
        // FXZERO R1: an engine turn that built zero parts is not
        // success, even on a clean stream end. A phrased question
        // keeps its answer status; a statement-like prompt fails.
        // summarizeEngineTurn already credits evidenced work (success
        // count, announced plan, solo marker): only a hollow summary
        // (not done, zero parts) flips the terminal status. Replays
        // (skipUserAppend) never flip: a replay slice is not the whole
        // run text, so zero parts in the slice prove nothing.
        const engineText = ranEngine || looksLikeEngineLog(answer);
        const terminalSummary = engineText
          ? summarizeEngineTurn(answer, "ok")
          : null;
        const questionPrompt = text.trimEnd().endsWith("?");
        // R8(b): a stop before any model call keeps its reason and
        // code; the verdict names it, never the generic retry line.
        const stopCode =
          terminalSummary?.stopReason === "no-model"
            ? "PROVIDER_NO_MODEL"
            : terminalSummary?.stopReason === "no-provider"
              ? "NO_PROVIDER_BOUND"
              : null;
        const emptyPlan =
          opts?.skipUserAppend !== true &&
          terminalSummary !== null &&
          !questionPrompt &&
          terminalSummary.parts === 0 &&
          !terminalSummary.done;
        const terminalStatus = emptyPlan ? "failed" : "ok";
        if (emptyPlan) {
          if (stopCode === null) {
            setChatHealth(key, "degraded");
          } else {
            setChatHealth(key, "ok");
          }
        } else {
          setChatHealth(key, "ok");
        }
        patchChatMessage(key, assistantId, { final: true });
        // The stream's own clean terminal event marks the waiting
        // proposal — the ONLY card path. Engine turns (executed) never
        // mark: they render the verdict view instead, live or reloaded.
        // FXCHATV V1: a run-log-looking text without the executed flag
        // is an engine reply too (legacy terminals): verdict plus
        // Details, never the card, never twice.
        if (ranEngine) {
          engineTurnStatus.set(assistantId, terminalStatus);
        } else if (looksLikeEngineLog(answer)) {
          engineTurnStatus.set(assistantId, terminalStatus);
        } else {
          proposalMessages.add(assistantId);
        }
        void recordTurnBestEffort(projectId, text, answer, {
          status: terminalStatus,
          run_id: runId,
          executed: ranEngine,
          ...(stopCode === null ? {} : { error_code: stopCode }),
        });
      }
      if (!mountedSlices.has(key)) {
        flagChatUnseen(key);
      }
    },
    (error: unknown) => {
      pumps.delete(key);
      emitPumpsChanged();
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
  const [draft, setDraft] = useState(() => props.initialDraft ?? getChatDraft(key));
  // FXUIB-B4: every keystroke lands in the per-slice store draft, so a
  // page change or remount revives it; a send clears it.
  function updateDraft(next: string): void {
    setChatDraft(key, next);
    setDraft(next);
  }
  const [teamMode, setTeamMode] = useState<"on" | "off">("on");
  // FXWHERE: project folder per run id (runs ledger), so the Done line
  // names where the files went. Best effort: unknown stays null and the
  // verdict keeps the pre-FXWHERE shape. Reloaded when the run ends
  // (the ledger row lands then) and when the project changes.
  const [runFolders, setRunFolders] = useState<Record<string, string>>({});
  const streamingRef = useRef(streaming);
  const loadedProjectRef = useRef<string | null>(null);
  useEffect(() => {
    const wasStreaming = streamingRef.current;
    streamingRef.current = streaming;
    const runEnded = wasStreaming === true && streaming === false;
    const projectChanged = loadedProjectRef.current !== props.projectId;
    if (!runEnded && !projectChanged) {
      return;
    }
    loadedProjectRef.current = props.projectId;
    let alive = true;
    void readLedgerWithRuns(props.projectId)
      .then(({ runs }) => {
        if (!alive) {
          return;
        }
        const next: Record<string, string> = {};
        for (const row of runs) {
          if (row.run_id !== "" && row.folder !== undefined && row.folder !== "") {
            next[row.run_id] = row.folder;
          }
        }
        setRunFolders(next);
      })
      .catch(() => {
        if (alive) {
          setRunFolders({});
        }
      });
    return () => {
      alive = false;
    };
    // Mount plus every run end (streaming true -> false).
  }, [props.projectId, streaming]);
  useEffect(() => {
    let alive = true;
    void readTeamMode(props.projectId)
      .then((stored) => {
        if (alive) {
          setTeamMode(stored.team);
        }
      })
      .catch(() => {
        if (alive) {
          setTeamMode("on");
        }
      });
    return () => {
      alive = false;
    };
  }, [props.projectId]);
  // FXCHATV (a): mirror for the batched no-provider restore below.
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [blocking, setBlocking] = useState<BlockingError | null>(() =>
    consumeBlockingStash(key),
  );
  // No model bound: the draft text stays so the user can connect a
  // provider and send the same task again. Never clobbers text the
  // user typed after the send. FXSTORE: a gone key restores the draft
  // too (reconnect, then send the same task again).
  useEffect(() => {
    if (
      blocking !== null &&
      (blocking.code === "NO_PROVIDER_BOUND" ||
        blocking.code === "SECRET_VALUE_MISSING") &&
      blocking.task !== undefined &&
      blocking.task.trim() !== "" &&
      draft.trim() === ""
    ) {
      updateDraft(blocking.task);
    }
  }, [blocking, draft]);
  const [toast, setToast] = useState<string | null>(null);
  const [flooded, setFlooded] = useState(false);
  // FXOPEN J6: the composer grows with the draft, about six lines.
  // The ref read stays inside the change handler and this effect, so
  // the rows follow restored drafts too (never a stuck one-liner).
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  function growComposer(): void {
    const area = promptRef.current;
    if (area === null) {
      return;
    }
    let line = 20;
    try {
      const parsed = parseFloat(
        window.getComputedStyle(area).lineHeight,
      );
      if (Number.isFinite(parsed) && parsed > 0) {
        line = parsed;
      }
    } catch {
      line = 20;
    }
    area.rows = composerRowsFor(draft, line, area.scrollHeight);
  }
  useEffect(() => {
    growComposer();
  });
  const offlineRef = useRef(!readOnline());
  const oneShotSentRef = useRef(false);
  const [pendingAsk, setPendingAsk] = useState<InstallPermissionAsk | null>(
    null,
  );
  // FXR1B: pinned argv behind the pending install ask, for the real
  // command display (never the raw tool key). Null until loaded or when
  // the ask carries no pinned words.
  const [askArgv, setAskArgv] = useState<readonly string[] | null>(null);
  useEffect(() => {
    if (pendingAsk === null) {
      setAskArgv(null);
      return;
    }
    let alive = true;
    void readInstallArgv(pendingAsk.toolName).then((argv) => {
      if (alive) {
        setAskArgv(argv);
      }
    });
    return () => {
      alive = false;
    };
  }, [pendingAsk]);
  // FXHARD1: earlier-page cursor from the served history page (null at
  // the oldest turn) plus the load-earlier busy flag.
  const [cursor, setCursor] = useState<string | null>(null);
  const [earlierBusy, setEarlierBusy] = useState(false);
  // FXCHATV (b): one Connect CTA per state. The composer hint hides
  // while the expanded hierarchy rows already offer the link (same
  // localStorage expansion the rows read).
  const [hierExpanded, setHierExpanded] = useState<boolean>(() => {
    try {
      return (
        window.localStorage.getItem(
          `agentsi.hierarchy.collapsed.${props.projectId}`,
        ) === "expanded"
      );
    } catch {
      return false;
    }
  });
  // FXCHATV V4: one ticking second hand while a run works; the step
  // line under the composer derives from the live deltas plus elapsed.
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!chatState.runner.streaming) {
      return;
    }
    const timer = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [chatState.runner.streaming]);
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
  // FXCHATV V3: the pending ask is project-keyed, so a hold that lands
  // under any slice key of this project (client swap, project switch,
  // remount) shows the card here without remount; the return restores
  // it from the stash or the stable per-project mirror.
  useEffect(() => {
    mountedSlices.add(key);
    markSeenByKey(key);
    try {
      setHierExpanded(
        window.localStorage.getItem(
          `agentsi.hierarchy.collapsed.${props.projectId}`,
        ) === "expanded",
      );
    } catch {
      setHierExpanded(false);
    }
    const stashedBlocking = consumeBlockingStash(key);
    if (stashedBlocking !== null) {
      setBlocking(stashedBlocking);
    }
    setPendingAsk(null);
    pendingAskRef.current = null;
    const stashedAsk = consumeProjectAsk(props.projectId);
    if (stashedAsk !== null) {
      if (isAssistantRunEnded(stashedAsk.messageId)) {
        // FXASK A7: its run really ended with no hold pending from it:
        // the card closes instead of restoring a dead dialog.
        clearProjectAsk(props.projectId);
        endedAssistants.delete(stashedAsk.messageId);
      } else {
        pendingAskRef.current = stashedAsk;
        setPendingAsk(stashedAsk);
      }
    }
    const ui: SliceUI = {
      onBlocking: (error) => {
        setBlocking(error);
        // FXCHATV (a): restore the task into the composer in the SAME
        // commit as the blocking error, so the draft is already back
        // when the error line lands. Same conditions as the effect
        // below (never clobbers text typed after the send); the effect
        // stays as the net for blocking restored at mount.
        if (
          error !== null &&
          error.code === "NO_PROVIDER_BOUND" &&
          error.task !== undefined &&
          error.task.trim() !== "" &&
          draftRef.current.trim() === ""
        ) {
          updateDraft(error.task);
        }
      },
      onAsk: (ask) => {
        pendingAskRef.current = ask;
        setPendingAsk(ask);
      },
    };
    sliceUI.set(key, ui);
    const unsubscribeAsk = subscribeProjectAsk(props.projectId, () => {
      const ask = readProjectAsk(props.projectId);
      if (ask !== null) {
        pendingAskRef.current = ask;
        setPendingAsk(ask);
      }
    });
    setChatOnline(key, readOnline());
    void loadHistoryOnce(key, props.projectId).then((next) => {
      setCursor(next);
    });
    return () => {
      unsubscribeAsk();
      mountedSlices.delete(key);
      // Leaving the page keeps the pending card: park it project-keyed
      // (plus the stable mirror) so the return restores the same dialog.
      if (pendingAskRef.current !== null) {
        parkProjectAsk(props.projectId, pendingAskRef.current);
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
    void readBoundModels(props.projectId).then(async (models) => {
      let known = models;
      if (models !== null && models.length === 0) {
        // A connected local runtime (Ollama, LM Studio) is a bound model
        // even though the cloud list is empty: no "No model bound" hint.
        const ids = await listConnectedProviders();
        if (ids.some((id) => id === "ollama" || id === "lm-studio")) {
          known = [{ local: true }];
        }
      }
      if (alive) {
        setBoundModels(known);
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
      updateDraft("");
      showToast(t("chat.stream.offline"));
      return;
    }
    updateDraft("");
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
      (err: unknown) => {
        // FXCLASS CD-8: the toast names the cause (code), never a bare
        // generic line that vanishes without a cause.
        const code = err instanceof ApiError ? err.code : "CONTEXT_MISSING";
        showToast(`${t(apiErrorLocaleKey(code))} (${code})`);
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

  // FXR1B: three answers for an install hold — "once" replays the
  // parked run and asks again next time, "project" records a
  // server-side installer grant (same head + subcommand, no widening
  // flags, this project only) and replays, "deny" closes the part with
  // a plain FAILED line and never resends. The card and the chat lines
  // name the real command, never the raw tool key.
  // FXASK A8: when the stream of that run is still open (mid-stream
  // ask, the run waits in place), answering only records the decision
  // (routes unchanged) and closes the card: no resend, the run itself
  // goes on. When no stream is open (fallback hold), as today.
  const answerAsk = (mode: "once" | "project" | "deny"): void => {
    const ask = pendingAskRef.current;
    if (ask === null) {
      return;
    }
    pendingAskRef.current = null;
    setPendingAsk(null);
    clearProjectAsk(props.projectId);
    const pump = pumps.get(key);
    const streamOpen =
      pump !== undefined && !pump.cancelled && pump.askOpen === true;
    if (pump !== undefined) {
      pump.askOpen = false;
    }
    const command = installDisplayCommand(
      ask.toolName,
      props.projectId,
      askArgv,
    );
    if (isInstallHoldTool(ask.toolName)) {
      if (mode === "project") {
        void recordProjectGrant(props.projectId, ask.toolName).then(
          () => {
            noteInstallAnswer(ask, command, true);
            if (!streamOpen) {
              replayParkedRun();
            }
          },
          () => {
            emitBlocking(key, {
              errorKey: "errors.generic",
              code: "UNKNOWN",
            });
          },
        );
        return;
      }
      if (mode === "deny") {
        // FXASKB B2: record the decision with the session token. Deny
        // closes the part with a plain FAILED line; the run does not
        // loop, so nothing resends.
        void requestResponse(PERMISSIONS_DECIDE_ROUTE, {
          method: "POST",
          kind: "write",
          body: {
            tool_id: ask.toolName,
            decision: "deny",
            project_id: props.projectId,
          },
        }).then(
          () => {
            const current = noteInstallAnswer(ask, command, false);
            const prompt = lastSentBySlice.get(key) ?? null;
            if (prompt !== null) {
              const runId = runIdBySlice.get(key) ?? "";
              void recordTurnBestEffort(props.projectId, prompt, current, {
                status: "failed",
                run_id: runId,
                error_code: "DENIED",
              });
            }
          },
          () => {
            emitBlocking(key, {
              errorKey: "errors.generic",
              code: "UNKNOWN",
            });
          },
        );
        return;
      }
      // FXASKB B2: record the decision with the session token, then
      // resend the same prompt automatically; the stored answer lets
      // the run continue without asking again.
      void requestResponse(PERMISSIONS_DECIDE_ROUTE, {
        method: "POST",
        kind: "write",
        body: {
          tool_id: ask.toolName,
          decision: "allow",
          project_id: props.projectId,
        },
      }).then(
        () => {
          noteInstallAnswer(ask, command, true);
          if (!streamOpen) {
            replayParkedRun();
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
        const note =
          mode === "deny"
            ? pt(
                "chat.permission.denied",
                "Install permission denied for {command}",
                { command },
              )
            : pt(
                "chat.permission.allowed",
                "Install permission granted for {command}",
                { command },
              );
        const current = getChatState(key).messages.find(
          (message) => message.id === ask.messageId,
        );
        if (current !== undefined) {
          patchChatMessage(key, ask.messageId, {
            text: current.text === "" ? note : `${current.text}\n${note}`,
            decided: mode === "deny" ? "rejected" : "accepted",
          });
        }
      },
      () => {
        emitBlocking(key, { errorKey: "errors.generic", code: "UNKNOWN" });
      },
    );
  };

  function noteInstallAnswer(
    ask: InstallPermissionAsk,
    command: string,
    granted: boolean,
  ): string {
    const note = granted
      ? pt(
          "chat.permission.allowed",
          "Install permission granted for {command}",
          { command },
        )
      : pt(
          "chat.permission.denied",
          "Install permission denied for {command}",
          { command },
        );
    const current = getChatState(key).messages.find(
      (message) => message.id === ask.messageId,
    );
    if (current !== undefined) {
      patchChatMessage(key, ask.messageId, {
        text: current.text === "" ? note : `${current.text}\n${note}`,
        decided: granted ? "accepted" : "rejected",
      });
      return current.text === "" ? note : `${current.text}\n${note}`;
    }
    return note;
  }

  function replayParkedRun(): void {
    const prompt = lastSentBySlice.get(key) ?? null;
    // Replay once, one visible user turn: the same prompt resends
    // without the user copy (the held message keeps only the receipt;
    // the terminal write upserts the opening run id into one stored
    // turn).
    if (prompt !== null) {
      const replayRunId = runIdBySlice.get(key);
      startChatRun(client, props.projectId, prompt, {
        skipUserAppend: true,
        ...(replayRunId === undefined ? {} : { runId: replayRunId }),
      });
    }
  }

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
  // FXCHATV V4: the live row is the newest unfinished assistant bubble.
  const liveRow = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && !message.final);
  const liveStep =
    streaming && liveRow !== undefined
      ? liveStepLine(liveRow.text, liveRow.at, nowMs)
      : null;

  return (
    <section data-testid="chat-area" aria-label={t("shell.sidebar.chat")}>
      {/* FXDESIGN6: the ref centre carries no card and no "Chat" heading;
          the h1 stays in the DOM for the frozen heading contract but reads
          as plain conversation (visually hidden). */}
      <h1 className="fx-vh">{t("shell.sidebar.chat")}</h1>
      {/* FXLOOK D2: the stream lane holds messages only; the hierarchy
          strip lives in the composer tray below, so the message lane is
          the single scroller of the column. */}
      <div
        data-testid="chat-layout"
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
              {message.role === "assistant" &&
              engineTurnStatus.has(message.id) ? (
                <EngineTurnView
                  text={message.text}
                  status={engineTurnStatus.get(message.id) ?? "ok"}
                  folder={folderForMessage(message.id, runFolders)}
                />
              ) : (
                <p style={{ whiteSpace: "pre-wrap" }}>
                  {shortProgramLine(message.text)}
                </p>
              )}{" "}
              {message.role === "assistant" &&
              message.final &&
              message.text !== "" ? (
                <>
                  <button
                    type="button"
                    data-testid="chat-copy"
                    className="fx-btn-quiet"
                    title={pt("chat.message.copy", "Copy")}
                    aria-label={pt("chat.message.copy", "Copy")}
                    onClick={() => {
                      copyQuiet(message.text);
                    }}
                  >
                    <CopyGlyph />
                  </button>{" "}
                </>
              ) : null}
              <time
                data-testid="chat-timestamp"
                title={t("chat.stream.timestamp")}
              >
                {formatChatTime(message.at)}
              </time>{" "}
              {message.resendPrompt !== undefined ? (
                <>
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
                  </button>{" "}
                </>
              ) : null}
              {message.role === "assistant" &&
              stoppedAssistants.has(message.id) ? (
                <>
                  <span
                    data-testid="chat-stopped-line"
                    role="status"
                    className="fx-quiet"
                  >
                    {pt("chat.stream.stopped", "Stopped")}
                  </span>{" "}
                </>
              ) : null}
              {/* FXCHATV V2: the card shows ONLY for a live plain
                  answer waiting for its verdict (Accept / Edit /
                  Reject): never on an engine turn (verdict view),
                  never stopped, never interrupted (resend), never
                  failed, never decided, never while streaming. */}
              {message.role === "assistant" &&
              proposalMessages.has(message.id) &&
              !engineTurnStatus.has(message.id) &&
              !stoppedAssistants.has(message.id) &&
              message.resendPrompt === undefined &&
              message.final &&
              message.text !== "" &&
              message.decided === undefined &&
              !streaming ? (
                <ApprovalCard
                  proposal={message.text}
                  onAccept={() => {
                    decide(message.id, "accepted");
                  }}
                  onEdit={(next) => {
                    updateDraft(next);
                  }}
                  onReject={() => {
                    decide(message.id, "rejected");
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>
        {messages.length === 0 ? (
          <div data-testid="chat-empty-state">
            <p>{t("chat.empty.line")}</p>
            {/* FXBTN: one spaced sample row; both read quiet. */}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button
              type="button"
              data-testid="chat-sample-1"
              className="fx-btn-quiet"
              onClick={() => {
                updateDraft(t("chat.empty.sample1"));
              }}
            >
              {t("chat.empty.sample1")}
            </button>
            <button
              type="button"
              data-testid="chat-sample-2"
              className="fx-btn-quiet"
              onClick={() => {
                updateDraft(t("chat.empty.sample2"));
              }}
            >
              {t("chat.empty.sample2")}
            </button>
            </div>
          </div>
        ) : null}
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
                "The run wants to execute “{command}”.",
                {
                  command: installDisplayCommand(
                    pendingAsk.toolName,
                    props.projectId,
                    askArgv,
                  ),
                },
              )}
            </p>
            <p data-testid="permission-why" className="fx-quiet">
              {pt(
                "chat.permission.why",
                "It installs packages the task needs to continue.",
              )}
            </p>
            <p data-testid="permission-tool">
              {installDisplayCommand(
                pendingAsk.toolName,
                props.projectId,
                askArgv,
              )}
            </p>
            {/* FXBTN: one spaced action row like other dialogs: allow once
                is the single primary, the project grant and deny read as
                quiet secondaries, never touching. */}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button
              type="button"
              data-testid="permission-allow"
              data-variant="primary"
              onClick={() => {
                answerAsk("once");
              }}
            >
              {pt("chat.permission.allowOnce", "Allow once")}
            </button>
            {isInstallHoldTool(pendingAsk.toolName) ? (
              <button
                type="button"
                data-testid="permission-allow-project"
                data-variant="quiet"
                onClick={() => {
                  answerAsk("project");
                }}
              >
                {pt("chat.permission.allowProject", "For this project")}
              </button>
            ) : null}
            <button
              type="button"
              data-testid="permission-deny"
              data-variant="quiet"
              onClick={() => {
                answerAsk("deny");
              }}
            >
              {pt("chat.permission.deny", "Deny")}
            </button>
            </div>
          </div>
        ) : null}
        {/* FXDESIGN6: one rounded box docked at the bottom: the field
            inside, the send as an icon button inside right; a small status
            line under it (model | route | working state). */}
        <div data-testid="chat-composer" className="fx-composer">
          {/* FXLOOK D2: the `Director: Auto ...` strip folds into the
              composer tray: one line at most (CSS ellipsis), so the
              column stays stream + pinned composer. */}
          <div data-testid="chat-tray" className="fx-composer-tray">
            <HierarchyRows
              projectId={props.projectId}
              onExpandedChange={setHierExpanded}
            />
          </div>
          <div>
            <span>{t("settings.project.team")}</span>
            <button
              type="button"
              data-testid="composer-team-toggle"
              className="fx-btn-quiet"
              aria-label={t("settings.project.team")}
              aria-pressed={teamMode === "on"}
              data-state={teamMode}
              title={t("settings.project.team")}
              onClick={() => {
                const next = teamMode === "on" ? "off" : "on";
                setTeamMode(next);
                void saveTeamMode(props.projectId, next)
                  .then((saved) => {
                    setTeamMode(saved.team);
                  })
                  .catch(() => {
                    setTeamMode(next);
                  });
              }}
            >
              {teamMode === "on"
                ? t("settings.project.teamOn")
                : t("settings.project.teamOff")}
            </button>
          </div>
          {/* FXCHATV (b): single Connect CTA for one state — the rows
              above already offer it when expanded and empty. */}
          {boundModels !== null &&
          boundModels.length === 0 &&
          blocking?.code !== "NO_PROVIDER_BOUND" &&
          !(
            connected !== null &&
            connected.length === 0 &&
            hierExpanded
          ) ? (
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
              <textarea
                data-testid="chat-prompt"
                ref={promptRef}
                id="chat-prompt"
                rows={1}
                placeholder={t("chat.composer.prompt")}
                aria-label={t("chat.composer.prompt")}
                value={draft}
                onChange={(event) => {
                  updateDraft(event.target.value);
                  growComposer();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
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
          <p
            data-testid="chat-statusline"
            className="fx-statusline"
            title={`${directorModel ?? t("chat.hierarchy.auto")} · ${statusRoute()}`}
          >            {/* FXDESIGN6: one span per value; the "|" dividers are CSS
                (no separator text nodes, so the locale-only contract
                sees exactly the three locale values). */}
            <span>{directorModel ?? t("chat.hierarchy.auto")}</span>
            <span>{statusRoute()}</span>
            <span>
              {/* FXCHATV (c): with no provider bound the status names
                  the blocked state, never Ready. */}
              {/* FXFACTS F9: a run waiting for a permission click shows
                  "Waiting for your answer" with no spin. */}
              {blocking?.code === "NO_PROVIDER_BOUND" ? (
                pt("chat.composer.statusBlocked", "Blocked")
              ) : pendingAsk !== null ? (
                <span data-testid="chat-waiting" role="status">
                  {t("chat.permission.waiting")}
                </span>
              ) : streaming ? (
                <>
                  <Spinner testId="chat-spinner" />
                  <span>{t("chat.composer.statusWorking")}</span>
                </>
              ) : (
                t("chat.composer.statusReady")
              )}
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
            <button
              type="button"
              data-testid="chat-abort"
              className="fx-btn-quiet"
              onClick={handleAbort}
            >
              {pendingAsk === null ? <Spinner /> : null}
              {t("chat.abort.cancel")}
            </button>
          ) : null}
          {/* FXCHATV V4: while a run works, the step line in plain
              words plus elapsed seconds sits under the composer. */}
          {liveStep !== null ? (
            <p data-testid="chat-live-step" role="status" className="fx-quiet">
              {liveStep}
            </p>
          ) : null}
          {online ? null : (
            <span data-testid="chat-offline-dot" role="status" className="fx-quiet">
              {t("chat.stream.offline")}
            </span>
          )}
          {blocking !== null ? (
            <div
              data-testid="chat-error-line"
              role="alert"
              className="fx-quiet"
            >
              <p>
                {chatErrorText(
                  blocking,
                  lastSentBySlice.get(key) ?? null,
                )}
              </p>
              {/* FXBTN: retry + connect share one spaced action row. */}
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                type="button"
                data-testid="kit-error-retry"
                className="fx-btn-quiet"
                onClick={handleRetry}
              >
                {t("chat.error.retry")}
              </button>
              {/* A2: the no-provider notice carries one action that gets
                  the user connected, next to Retry (same target as the
                  composer hint). FXSTORE: a gone key links Settings too.
                  R8(b): a no-model stop links the same fix. */}
              {blocking.code === "NO_PROVIDER_BOUND" ||
              blocking.code === "PROVIDER_NO_MODEL" ||
              blocking.code === "SECRET_VALUE_MISSING" ||
              blocking.errorKey === "firstrun.steps.connectProvider" ? (
                <a
                  data-testid="kit-error-connect"
                  className="fx-btn-quiet"
                  href="/settings/models"
                >
                  {t("chat.hierarchy.connect")}
                </a>
              ) : null}
              </div>
            </div>
          ) : null}
          {blocking === null && health === "degraded" && !streaming ? (
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
        {toast !== null ? (
          <div data-testid="chat-toast" role="status">
            {toast}
          </div>
        ) : null}
      </div>
    </section>
  );
}
