// Secret-store port for the ProvidersPage lane.
// The store holds references only (SecretRef carries no key material).
// Deletions are audit-logged by entry name only.

import { APP_NAMESPACE_PREFIX } from "./types";
import type { SecretRef } from "./types";

export type AuditRecord = {
  action: "save" | "delete";
  entryName: string;
  at: string;
};

export interface SecretStorePort {
  list(prefix: string): Promise<SecretRef[]>;
  save(ref: SecretRef): Promise<void>;
  remove(secretId: string, sessionToken: string): Promise<void>;
  audit(): AuditRecord[];
}

export function secretIdForProvider(providerId: string): string {
  return `${APP_NAMESPACE_PREFIX}${providerId}`;
}

export function createMemorySecretStore(sessionToken: string): SecretStorePort {
  const entries = new Map<string, SecretRef>();
  const trail: AuditRecord[] = [];
  const now = (): string => new Date().toISOString();
  return {
    async list(prefix: string): Promise<SecretRef[]> {
      return [...entries.values()].filter((entry) => entry.secret_id.startsWith(prefix));
    },
    async save(ref: SecretRef): Promise<void> {
      entries.set(ref.secret_id, ref);
      trail.push({ action: "save", entryName: ref.secret_id, at: now() });
    },
    async remove(secretId: string, token: string): Promise<void> {
      if (token.length === 0 || token !== sessionToken) {
        throw new Error("Invalid session token.");
      }
      if (!entries.has(secretId)) {
        throw new Error("Entry not found.");
      }
      entries.delete(secretId);
      trail.push({ action: "delete", entryName: secretId, at: now() });
    },
    audit(): AuditRecord[] {
      return [...trail];
    },
  };
}
