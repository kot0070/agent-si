// K07NEXT4 LIVE0B-05: the Chat message box that starts a task.
import { useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { startChatTaskDoc } from "./k07next4Api";
import type { ChatTaskDoc } from "./k07next4Api";

export function ChatTaskBox(): ReactElement {
  const [draft, setDraft] = useState("");
  const [started, setStarted] = useState<ChatTaskDoc | null>(null);
  async function send(): Promise<void> {
    const next = await startChatTaskDoc(draft).catch(() => undefined);
    if (next !== undefined) {
      setStarted(next);
    }
  }
  return (
    <section data-testid="k07next4-chat-task">
      <h2>{t("shell.sidebar.chat")}</h2>
      <input
        aria-label={t("chat.composer.prompt")}
        placeholder={t("chat.composer.prompt")}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
      />
      <button type="button" onClick={() => void send()}>
        {t("chat.composer.send")}
      </button>
      {started === null ? (
        <p>{t("chat.composer.draft")}</p>
      ) : (
        <p>{started.status}</p>
      )}
    </section>
  );
}
