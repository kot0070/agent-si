// K04 D15 contract types (types ONLY, zero runtime code).
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
  // Step-2 additions (all optional; omitting them keeps the old key-only
  // contract). initialStep 2 opens Manage-models directly; a non-empty
  // initialTicked seeds the ticks (empty falls back to the recommended
  // text model); the served enabled list wins when present; Done reports
  // (preset_id, tickedIds) through onModelsDone. Proved in
  // k04-iface.contract.test.tsx "step-2 props".
  initialStep?: 1 | 2;
  initialTicked?: string[];
  onModelsDone?: (presetId: string, modelIds: string[]) => void;
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
  deleteEntry?: (entry: SecretRef) => Promise<void>;
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
