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
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { DEFAULT_LOCALE, formatDate, t } from "../locale/index";
import enTable from "../locale/en.json";
import { ErrorPanel } from "../ui/ErrorPanel";
import { ApprovalCard } from "./ApprovalCard";
import {
  CHAT_FLOOD_WINDOW_MS,
  compactPrompt,
  extractChatTags,
  isFlooding,
  streamChat,
} from "./chatApi";
import type { ChatRunner } from "./chatApi";
import {
  askPermission,
  isInstallPermissionAsk,
  pt,
} from "./permissions";
import type { InstallPermissionAsk } from "./permissions";

export interface ChatAreaProps {
  projectId: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: number;
  final: boolean;
  decided?: "accepted" | "rejected";
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

export function ChatArea(props: ChatAreaProps): ReactElement {
  const client = useApiClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
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
  const runnerRef = useRef<ChatRunner | null>(null);
  const [pendingAsk, setPendingAsk] = useState<InstallPermissionAsk | null>(
    null,
  );
  const pendingAskRef = useRef<InstallPermissionAsk | null>(null);
  const cancelRef = useRef(false);
  const streamingRef = useRef(false);
  const lastSentRef = useRef<string | null>(null);

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
      ({ aborted }) => {
        runnerRef.current = null;
        streamingRef.current = false;
        setStreaming(false);
        if (!aborted) {
          setHealth("ok");
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? { ...message, final: !aborted }
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
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id ? { ...message, decided } : message,
      ),
    );
  };

  const channelLocale = readChannelLocale();
  const channelTags = messages.flatMap((message) =>
    message.role === "assistant" ? extractChatTags(message.text) : [],
  );
  const visibleTags = [...new Set(channelTags)];

  return (
    <section data-testid="chat-area" aria-label={t("shell.sidebar.chat")}>
      <div data-testid="chat-layout">
        <div data-testid="chat-messages">
          {messages.map((message) => (
            <div
              key={message.id}
              data-testid={
                message.role === "user"
                  ? "chat-user-message"
                  : "chat-assistant-message"
              }
            >
              <p>{message.text}</p>
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
        <div data-testid="chat-composer">
          {draft !== "" ? (
            <span data-testid="chat-draft-chip">{t("chat.composer.draft")}</span>
          ) : null}
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
          <button
            type="button"
            data-testid="chat-send"
            disabled={draft.trim() === "" || streaming}
            onClick={handleSend}
          >
            {t("chat.composer.send")}
          </button>
          {streaming ? (
            <span data-testid="chat-spinner" role="status">
              {t("chat.stream.spinner")}
            </span>
          ) : null}
          {streaming ? (
            <button type="button" data-testid="chat-abort" onClick={handleAbort}>
              {t("chat.abort.cancel")}
            </button>
          ) : null}
          {online ? null : (
            <span data-testid="chat-offline-dot" role="status">
              {t("chat.stream.offline")}
            </span>
          )}
          {health === "degraded" ? (
            <span data-testid="chat-health-degraded" role="status">
              {t("errors.generic")}
            </span>
          ) : null}
          {health === "reconnecting" ? (
            <span data-testid="chat-health-reconnecting" role="status">
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
