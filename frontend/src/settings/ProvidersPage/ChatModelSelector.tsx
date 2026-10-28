// ChatModelSelector: project-scoped chat model picker (frozen section 3.8 name).
// Lists enabled models only, by label. Thin wrapper over ChatSelector, which
// stays as the underlying picker so existing call sites keep working.
// The catalog and states are module defaults; the pick is uncontrolled state.

import { useState } from "react";
import { PROVIDER_CATALOG } from "./catalog";
import { ChatSelector } from "./ChatSelector";
import type { ProviderState } from "./types";

type ChatModelSelectorProps = {
  project_id: string;
  states?: Record<string, ProviderState>;
};

export function ChatModelSelector({ project_id = "local", states = {} }: ChatModelSelectorProps) {
  const catalog = PROVIDER_CATALOG;
  const [value, setValue] = useState("");
  return (
    <div data-testid="chat-model-selector" data-project-id={project_id}>
      <ChatSelector catalog={catalog} states={states} value={value} onChange={setValue} />
    </div>
  );
}
