// Lane A ChatArea in frontend/src/chat/index.tsx: the mounted chat surface.
// Chat-first layout (messages plus composer; no graph canvas anywhere).
// Renders the prompt plus streamed tokens incrementally over the shared
// ApiClient entry; draft chip plus spinner plus timestamp; an offline queue
// dot while disconnected (prompts queue and flush on reconnect); abort
// cancels the stream cleanly. Background failures toast; blocking errors
// render inline. Channel meta shows the channel locale policy plus the tags
// served inside assistant deltas; rapid sends raise a flooding warning with
// a compact re-issue action; stream failure marks the channel degraded and
// an offline-to-online return marks it reconnecting until the next stream
// Production caller: wave-3 App chat route
// (CODER-5-Vale frontend/src/app/App.tsx); owned test mounts this component.
// FXASK: install-permission dialog (F2) answers APPROVAL_REQUIRED holds via F1.

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { useApiClient } from "../app/ApiClientProvider";
import { ApiError, apiErrorLocaleKey, requestResponse } from "../api/errors";
import { DEFAULT_LOCALE, formatDate, t } from "../locale/index";
import enTable from "../locale/en.json";
import { ErrorPanel } from "../ui/ErrorPanel";
import { ApprovalCard } from "./ApprovalCard";
import { HierarchyRows } from "./HierarchyRows";
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

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: number;
  final: boolean;
  decided?: "accepted" | "rejected";
  // D6(b): the done event of an executed engine turn marks its answer;
  // the verdict card is withheld under finished engine runs (nothing to
  // accept: the work already happened) and kept for plain answers.
  engineRun?: boolean;
}

interface BlockingError {
  errorKey: string;
  code: string;
}

let streamSeq = 0;
let messageSeq = 0;

function nextStreamId(): string {
  streamSeq += 1;
  return `chat-stream-${Date.now()}-${streamSeq}`;
}

function nextMessageId(): string {
  messageSeq += 1;
  return `chat-message-${Date.now()}-${messageSeq}`;
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

export function ChatArea(props: ChatAreaProps): ReactElement {
  const client = useApiClient();
  const [boundModels, setBoundModels] = useState<unknown[] | null>(null);
  const [connected, setConnected] = useState<string[] | null>(null);
  const [directorModel, setDirectorModel] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState(props.initialDraft ?? "");
  const [streaming, setStreaming] = useState(false);
  const [blocking, setBlocking] = useState<BlockingError | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [online, setOnline] = useState(readOnline);
  const [queue, setQueue] = useState<string[]>([]);
  const [flooded, setFlooded] = useState(false);
  const [health, setHealth] = useState<"ok" | "degraded" | "reconnecting">(
    "ok",
  );
  const sendTimesRef = useRef<number[]>([]);
  const offlineRef = useRef(!readOnline());
  const oneShotSentRef = useRef(false);
  const runnerRef = useRef<ChatRunner | null>(null);
  const [pendingAsk, setPendingAsk] = useState<InstallPermissionAsk | null>(
    null,
  );
  const pendingAskRef = useRef<InstallPermissionAsk | null>(null);
  const cancelRef = useRef(false);
  const streamingRef = useRef(false);
  const lastSentRef = useRef<string | null>(null);
  // FXRC1FIX P3: the message list owns the scroll inside the chat card;
  // the composer sits below it in flow and never overlays text. stick
  // follows the newest message unless the user scrolled up.
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    const onOnline = (): void => {
      setOnline(true);
      if (offlineRef.current) {
        offlineRef.current = false;
        setHealth("reconnecting");
      }
    };
    const onOffline = (): void => {
      offlineRef.current = true;
      setOnline(false);
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(
    () => () => {
      cancelRef.current = true;
      const runner = runnerRef.current;
      if (runner !== null) {
        runner.cancel().then(
          () => undefined,
          () => undefined,
        );
      }
    },
    [],
  );

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

  const sendPrompt = (text: string): void => {
    const prompt = text.trim();
    if (prompt === "" || streamingRef.current) {
      return;
    }
    cancelRef.current = false;
    lastSentRef.current = prompt;
    const sentAt = Date.now();
    const recentSends = [
      ...sendTimesRef.current.filter((at) => sentAt - at < CHAT_FLOOD_WINDOW_MS),
      sentAt,
    ];
    sendTimesRef.current = recentSends;
    if (isFlooding(recentSends, sentAt)) {
      setFlooded(true);
    }
    setBlocking(null);
    setToast(null);
    const userId = nextMessageId();
    const assistantId = nextMessageId();
    const at = Date.now();
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", text: prompt, at, final: true },
      { id: assistantId, role: "assistant", text: "", at, final: false },
    ]);
    setStreaming(true);
    streamingRef.current = true;
    const runner = streamChat(
      client,
      { project_id: props.projectId, prompt_ref: prompt, stream_id: nextStreamId() },
      {
        onChunkText: (delta) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, text: message.text + delta }
                : message,
            ),
          );
        },
        isCancelled: () => cancelRef.current,
      },
    );
    runnerRef.current = runner;
    runner.done.then(
      ({ aborted, executed }) => {
        runnerRef.current = null;
        streamingRef.current = false;
        setStreaming(false);
        if (!aborted) {
          setHealth("ok");
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? { ...message, final: !aborted, engineRun: executed }
              : message,
          ),
        );
      },
      (error: unknown) => {
        runnerRef.current = null;
        streamingRef.current = false;
        setStreaming(false);
        if (isInstallPermissionAsk(error)) {
          // FXASK2: the run is held for install permission (served
          // approval event). The held message stays final so the answer is
          // recorded on the run; the F1 ask-once ledger decides whether the
          // dialog shows at all. The tool is the event's own tool id
          // (guard tool_name), answered once per tool — never a
          // project-derived key.
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, final: true }
                : message,
            ),
          );
          const toolName = (error as ApiError).toolId as string;
          if (isInstallHoldTool(toolName)) {
            // FXASKB B1 hold: the dialog shows regardless of the
            // asked-once flag; Allow/Deny records the decision and the
            // same prompt resends, so the run continues stored and
            // never asks again. The tool is the command's own id.
            if (pendingAskRef.current?.toolName === toolName) {
              return;
            }
            pendingAskRef.current = { toolName, messageId: assistantId };
            setPendingAsk({ toolName, messageId: assistantId });
            return;
          }
          if (pendingAskRef.current?.toolName === toolName) {
            return;
          }
          void askPermission(toolName).then(
            (outcome) => {
              if (outcome.askedOnce) {
                // Stored answer: the second run of that tool does not ask.
                return;
              }
              pendingAskRef.current = { toolName, messageId: assistantId };
              setPendingAsk({ toolName, messageId: assistantId });
            },
            () => {
              pendingAskRef.current = { toolName, messageId: assistantId };
              setPendingAsk({ toolName, messageId: assistantId });
            },
          );
          return;
        }
        setMessages((prev) =>
          prev
            .map((message) =>
              message.id === assistantId
                ? { ...message, final: false }
                : message,
            )
            .filter(
              (message) => message.id !== assistantId || message.text !== "",
            ),
        );
        setHealth("degraded");
        if (error instanceof ApiError) {
          setBlocking({ errorKey: apiErrorLocaleKey(error.code), code: error.code });
        } else {
          setBlocking({ errorKey: "errors.generic", code: "UNKNOWN" });
        }
      },
    );
  };

  // First-message one-shot: the start box created the project plus
  // task already, so the kept message sends once through the existing
  // sendPrompt on mount, guarded against double effects, then the
  // parent clears it. initialDraft keeps filling without sending.
  useEffect(() => {
    if (
      props.initialSend !== undefined &&
      props.initialSend !== "" &&
      !oneShotSentRef.current
    ) {
      oneShotSentRef.current = true;
      sendPrompt(props.initialSend);
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
      setQueue((prev) => prev.slice(1));
      sendPrompt(next);
    }
  });

  const handleSend = (): void => {
    const prompt = draft.trim();
    if (prompt === "" || streaming) {
      return;
    }
    if (!online) {
      setQueue((prev) => [...prev, prompt]);
      setDraft("");
      setToast(t("chat.stream.offline"));
      return;
    }
    setDraft("");
    sendPrompt(prompt);
  };

  const handleAbort = (): void => {
    const runner = runnerRef.current;
    if (runner === null) {
      return;
    }
    cancelRef.current = true;
    runner.cancel().then(
      () => undefined,
      () => {
        setToast(t("errors.generic"));
      },
    );
  };

  const handleRetry = (): void => {
    const prompt = lastSentRef.current;
    if (prompt === null || streaming) {
      return;
    }
    setBlocking(null);
    if (!online) {
      setQueue((prev) => [...prev, prompt]);
      return;
    }
    sendPrompt(prompt);
  };

  const handleCompactResend = (): void => {
    const prompt = lastSentRef.current;
    if (prompt === null || streaming) {
      return;
    }
    const compacted = compactPrompt(prompt);
    sendTimesRef.current = [];
    setFlooded(false);
    setBlocking(null);
    if (!online) {
      setQueue((prev) => [...prev, compacted]);
      return;
    }
    sendPrompt(compacted);
  };

  const answerAsk = (allow: boolean): void => {
    const ask = pendingAskRef.current;
    if (ask === null) {
      return;
    }
    pendingAskRef.current = null;
    setPendingAsk(null);
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
          setMessages((prev) =>
            prev.map((message) =>
              message.id === ask.messageId
                ? {
                    ...message,
                    text:
                      message.text === ""
                        ? note
                        : `${message.text}
${note}`,
                    decided: allow ? "accepted" : "rejected",
                  }
                : message,
            ),
          );
          const prompt = lastSentRef.current;
          if (prompt !== null && !streamingRef.current) {
            sendPrompt(prompt);
          }
        },
        () => {
          setBlocking({ errorKey: "errors.generic", code: "UNKNOWN" });
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
        setMessages((prev) =>
          prev.map((message) =>
            message.id === ask.messageId
              ? {
                  ...message,
                  text:
                    message.text === ""
                      ? note
                      : `${message.text}
${note}`,
                  decided: allow ? "accepted" : "rejected",
                }
              : message,
          ),
        );
      },
      () => {
        setBlocking({ errorKey: "errors.generic", code: "UNKNOWN" });
      },
    );
  };

  const decide = (id: string, decided: "accepted" | "rejected"): void => {
    const proposal =
      messages.find((message) => message.id === id)?.text ?? "";
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id ? { ...message, decided } : message,
      ),
    );
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
                {formatDate(new Date(message.at))}
              </time>
              {message.role === "assistant" &&
              message.final &&
              message.text !== "" &&
              message.decided === undefined &&
              message.engineRun !== true &&
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
          <p data-testid="chat-statusline" className="fx-statusline">
            {/* FXDESIGN6: one span per value; the "|" dividers are CSS
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
