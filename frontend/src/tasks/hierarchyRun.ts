// Lane A hierarchy run helper: starts the integration task only over stored
// gate plus audit PASS refs (K02 validation V1: no close_part without stored
// gate PASS plus stored audit PASS; V2: no early start without refs resolved
// to stored gate plus audit PASS; chain activation per C20
// delta.activate_hierarchy_chain, dispatch per C19 graph.validate_dispatch).
// Any other combination refuses with the frozen K02 section 6 code and
// mutates nothing. Production caller: wave-3 App project-tasks route
// (CODER-5-Vale frontend/src/app/App.tsx); owned test refuses and accepts.

import { z } from "zod";
import type { ApiClient, TaskRecord } from "../api/iface";
import { ApiError } from "../api/errors";

const GateStateSchema = z.enum(["PASS", "BLOCKED"]);

export type GateState = z.infer<typeof GateStateSchema>;

const StoredGateRefsSchema = z.object({
  packageId: z.string().min(1),
  gate: GateStateSchema,
  audit: GateStateSchema,
  evidenceRefs: z.array(z.string().min(1)).min(1),
});

export interface StoredGateRefs {
  packageId: string;
  gate: GateState;
  audit: GateState;
  evidenceRefs: string[];
}

const HierarchyRunSchema = z.object({
  projectId: z.string().min(1),
  title: z.string().min(1),
  scope: z.array(z.string()),
});

export interface HierarchyRunInput {
  projectId: string;
  title: string;
  scope: string[];
  refs: StoredGateRefs;
}

export async function startHierarchyRun(
  client: ApiClient,
  input: HierarchyRunInput,
): Promise<TaskRecord> {
  const checked = HierarchyRunSchema.safeParse({
    projectId: input.projectId,
    title: input.title,
    scope: input.scope,
  });
  if (!checked.success) {
    throw new ApiError("CONTEXT_WRONG_CONTRACT_VERSION", 400);
  }
  const refs = StoredGateRefsSchema.safeParse(input.refs);
  if (!refs.success) {
    throw new ApiError("INVALID_HIERARCHY_CHAIN", 409);
  }
  if (refs.data.gate !== "PASS") {
    throw new ApiError("GATE_NOT_PASSED", 409);
  }
  if (refs.data.audit !== "PASS") {
    throw new ApiError("AUDIT_INDEPENDENCE_REJECTED", 403);
  }
  return client.createTask(checked.data.projectId, {
    title: checked.data.title,
    scope: checked.data.scope,
  });
}
