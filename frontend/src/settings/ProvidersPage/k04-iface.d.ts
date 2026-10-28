// K04 D15 contract stub (types ONLY, zero runtime code).
// Product code never imports this file; the contract test type-checks
// the real components' props against these interfaces.

import type { ProviderPreset, SecretRef } from "./types";
import type { SecretStorePort } from "./secretStore";

export interface ConnectDialogProps {
  preset_id: string;
  preset: ProviderPreset | null;
  open: boolean;
  store: SecretStorePort;
  timeoutMs?: number;
  onClose: () => void;
  onConnected: (presetId: string, ref: SecretRef) => void;
}

export interface DisconnectDialogProps {
  provider_id: string;
  providerLabel: string;
  secretId: string;
  open: boolean;
  store: SecretStorePort;
  sessionToken: string;
  onClose: () => void;
  onDisconnected: (secretId: string) => void;
}

export interface LeftoverKeyFinderProps {
  store: SecretStorePort;
  sessionToken: string;
  linkedSecretIds: string[];
  refreshKey?: number;
  loadEntries?: () => Promise<SecretRef[]>;
}

// K04 CLOSE (chat-model save): JSON body of PUT /api/v1/roles/chat-model
// (see saveChatModel in ProvidersPage.tsx) plus its 200 payload.
export interface ChatModelSaveRequest {
  project_id: string;
  model_id: string;
}

export interface ChatModelSaveResult {
  ok: boolean;
  project_id: string;
  model_id: string;
}
