// Lane A ChatArea in frontend/src/chat/index.tsx: the mounted chat surface.
// Chat-first layout (messages plus composer; no graph canvas anywhere).
// Renders the prompt plus streamed tokens incrementally over the shared
// ApiClient entry; draft chip plus spinner plus timestamp; an offline queue
// dot while disconnected (prompts queue and flush on reconnect); abort
// cancels the stream cleanly. Background failures toast; blocking errors
// render inline. Production caller: wave-3 App chat route
// (CODER-5-Vale frontend/src/app/App.tsx); owned test mounts this component.

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { useApiClient } from "../app/ApiClientProvider";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { formatDate, t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import { ApprovalCard } from "./ApprovalCard";
import { streamChat } from "./chatApi";
import type { ChatRunner } from "./chatApi";

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

export function ChatArea(props: ChatAreaProps): ReactElement {
  const client = useApiClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [blocking, setBlocking] = useState<BlockingError | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [online, setOnline] = useState(readOnline);
  const [queue, setQueue] = useState<string[]>([]);
  const runnerRef = useRef<ChatRunner | null>(null);
  const cancelRef = useRef(false);
  const streamingRef = useRef(false);
  const lastSentRef = useRef<string | null>(null);

  useEffect(() => {
    const onOnline = (): void => {
      setOnline(true);
    };
    const onOffline = (): void => {
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

  const decide = (id: string, decided: "accepted" | "rejected"): void => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id ? { ...message, decided } : message,
      ),
    );
  };

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
        </div>
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
