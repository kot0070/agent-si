// K07NEXT2 split B: read functions over already-served backend routes.
// Each reader quotes the server-shaped schema of its backend route
// (src/agent_si/backend/*.py); only global fetch is ever replaced.
import { z } from "zod";
import { requestJson } from "../api/errors";

// M-R-UX-3: the project list over the served projects read route
// (src/agent_si/backend/read_routes.py:168 project_view).
export const ProjectsDocSchema = z.object({
  projects: z.array(
    z.object({
      project_id: z.string().min(1),
      name: z.string().min(1),
      folder_ref: z.string().min(1),
      created_at: z.string().min(1),
    }),
  ),
});

export type ProjectsDoc = z.infer<typeof ProjectsDocSchema>;

export async function readProjectsDoc(): Promise<ProjectsDoc> {
  return requestJson(
    "/api/v1/projects",
    { method: "GET", kind: "read" },
    ProjectsDocSchema,
  );
}

// M-R-UX-4: the local runtime status over the served local status route
// (src/agent_si/backend/local_connect.py:36 LocalStatus).
export const LocalStatusDocSchema = z.object({
  status: z.string().min(1),
  reason: z.string().min(1),
});

export type LocalStatusDoc = z.infer<typeof LocalStatusDocSchema>;

export async function readLocalStatusDoc(): Promise<LocalStatusDoc> {
  return requestJson(
    "/api/v1/local/status",
    { method: "GET", kind: "read" },
    LocalStatusDocSchema,
  );
}

// M-R-UX-6: the known local models over the served local models route
// (src/agent_si/backend/local_connect.py:42 LocalModelRow).
export const LocalModelsDocSchema = z.array(
  z.object({
    model: z.string().min(1),
    evidence_tier: z.string().min(1),
    status: z.string().min(1),
  }),
);

export type LocalModelsDoc = z.infer<typeof LocalModelsDocSchema>;

export async function readLocalModelsDoc(): Promise<LocalModelsDoc> {
  return requestJson(
    "/api/v1/local/models",
    { method: "GET", kind: "read" },
    LocalModelsDocSchema,
  );
}

// M-R-UX-8: the telemetry aggregates over the served analytics route
// (src/agent_si/backend/read_routes.py:300 read_telemetry_analytics).
export const TelemetryDocSchema = z.object({
  metric_records: z.number(),
  telemetry_events: z.number(),
  totals: z.record(z.string(), z.number()),
  tasks: z.array(z.string()),
});

export type TelemetryDoc = z.infer<typeof TelemetryDocSchema>;

export async function readTelemetryDoc(): Promise<TelemetryDoc> {
  return requestJson(
    "/api/v1/analytics/telemetry",
    { method: "GET", kind: "read" },
    TelemetryDocSchema,
  );
}

// FXDESIGN8: the project-scoped telemetry doc (?project_id=) carries the
// same legacy totals plus per-model and per-provider aggregates from the
// store readers. Tokens/cost read "UNAVAILABLE" when unevidenced.
const TelemetryUsageRowSchema = z.object({
  calls: z.number().int(),
  tokens: z.union([z.number(), z.string()]),
  cost: z.union([z.number(), z.string()]),
});

const ProjectTelemetrySchema = TelemetryDocSchema.extend({
  models: z
    .array(TelemetryUsageRowSchema.extend({ model: z.string() }))
    .optional(),
  providers: z
    .array(TelemetryUsageRowSchema.extend({ provider: z.string() }))
    .optional(),
  // FXTELEM roles: per-role-per-model aggregates (same events as the
  // models rows, grouped by the role recorded at record time). Role ""
  // buckets role-less calls and renders as Other calls.
  roles: z
    .array(
      TelemetryUsageRowSchema.extend({
        role: z.string(),
        model: z.string(),
      }),
    )
    .optional(),
});

export type ProjectTelemetry = z.infer<typeof ProjectTelemetrySchema>;

export async function readProjectTelemetry(
  projectId: string,
): Promise<ProjectTelemetry> {
  return requestJson(
    `/api/v1/analytics/telemetry?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    ProjectTelemetrySchema,
  );
}

// M-R-UX-9: the knowledge base refresh proposal over the served
// kb refresh route (src/agent_si/backend/app.py:1579).
export const KbProposalDocSchema = z.object({
  kb_id: z.string().nullable(),
  stale: z.boolean(),
  proposals: z.array(z.object({}).passthrough()),
});

export type KbProposalDoc = z.infer<typeof KbProposalDocSchema>;

export async function readKbProposalDoc(): Promise<KbProposalDoc> {
  return requestJson(
    "/api/v1/kb/refresh/proposal",
    { method: "GET", kind: "read" },
    KbProposalDocSchema,
  );
}

// M-R-UX-10: the package ledger rows over the served runs ledger route
// (src/agent_si/backend/app.py:131 runs_ledger).
export const RunsLedgerDocSchema = z.object({
  rows: z.array(
    z.object({
      package_id: z.string().min(1),
      agents: z.number().int().min(0),
      peak_concurrency: z.number().int().min(0),
      wall_time_s: z.number().min(0),
    }),
  ),
});

export type RunsLedgerDoc = z.infer<typeof RunsLedgerDocSchema>;

export async function readRunsLedgerDoc(
  projectId: string,
): Promise<RunsLedgerDoc> {
  return requestJson(
    `/api/v1/runs/ledger?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    RunsLedgerDocSchema,
  );
}

// M-R-UX-12: the bench gateway check over the served localbench check
// route (src/agent_si/backend/localbench_routes.py:223).
export const BenchCheckDocSchema = z.object({
  reachable: z.boolean(),
  reason: z.string().min(1),
});

export type BenchCheckDoc = z.infer<typeof BenchCheckDocSchema>;

export async function readBenchCheckDoc(): Promise<BenchCheckDoc> {
  return requestJson(
    "/api/v1/local/bench/check",
    { method: "GET", kind: "read" },
    BenchCheckDocSchema,
  );
}
