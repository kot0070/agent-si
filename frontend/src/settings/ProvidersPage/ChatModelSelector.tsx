// ChatModelSelector: project-scoped chat model picker (frozen section 3.8 name).
// Lists enabled models only, by label. Thin wrapper over ChatSelector, which
// stays as the underlying picker so existing call sites keep working.
// The catalog and states are module defaults; the pick is uncontrolled state.
// The optional onChange reports the picked model id so the page can persist it.

import { useState } from "react";
import { PROVIDER_CATALOG } from "./catalog";
import { ChatSelector } from "./ChatSelector";
import type { ProviderState } from "./types";

type ChatModelSelectorProps = {
  project_id: string;
  states?: Record<string, ProviderState>;
  onChange?: (modelId: string) => void;
};

export function ChatModelSelector({ project_id = "local", states = {}, onChange }: ChatModelSelectorProps) {
  const catalog = PROVIDER_CATALOG;
  const [value, setValue] = useState("");
  function handleChange(modelId: string): void {
    setValue(modelId);
    if (onChange) {
      onChange(modelId);
    }
  }
  return (
    <div data-testid="chat-model-selector" data-project-id={project_id}>
      <ChatSelector catalog={catalog} states={states} value={value} onChange={handleChange} />
    </div>
  );
}
