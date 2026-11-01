// Public surface of the ProvidersPage lane.

export { PROVIDER_CATALOG, catalogOrder, getPreset } from "./catalog";
export { ChatSelector, enabledChatChoices } from "./ChatSelector";
export type { ChatChoice } from "./ChatSelector";
export { CONNECT_TIMEOUT_MS, ConnectDialog, saveWithTimeout } from "./ConnectDialog";
export type { ConnectResult } from "./ConnectDialog";
export { DisconnectDialog } from "./DisconnectDialog";
export { LeftoverFinder } from "./LeftoverFinder";
export { ProvidersPage } from "./ProvidersPage";
export { createMemorySecretStore, secretIdForProvider } from "./secretStore";
export type { AuditRecord, SecretStorePort } from "./secretStore";
export { APP_NAMESPACE_PREFIX, AUTO_SENTINEL, ROLE_KEYS, ROLE_LABELS, roleLabel } from "./types";
export type {
  ModelOption,
  ProviderKind,
  ProviderPreset,
  ProviderState,
  RoleAssignment,
  RoleKey,
  SecretRef,
} from "./types";
export { SetupWizard } from "./SetupWizard";
export { ChatModelSelector } from "./ChatModelSelector";
export { LeftoverKeyFinder } from "./LeftoverKeyFinder";
export type { LeftoverKeyFinderProps } from "./LeftoverKeyFinder";
export {
  POOL_STRATEGY_LABELS,
  RolePoolPicker,
  choicesToPoolOptions,
  defaultPoolResolver,
} from "./RolePoolPicker";
export type {
  PoolOption,
  PoolStrategy,
  ResolvedChoice,
  RolePoolMode,
  RolePoolValue,
} from "./RolePoolPicker";
