// K07NEXT5 readers over the served k07next5 backend routes.
// Each reader quotes the server-shaped schema of its backend route
// (src/agent_si/http/k07next5.py); only global fetch is ever replaced.
import { z } from "zod";
import { requestJson } from "../api/errors";

// 111-UI: the local AI settings write plus its decision record over the
// served decision update route (src/agent_si/http/k07next5.py
// local_ai_decision_update, quoting update_config plus record_decision
// in src/agent_si/local/config.py).
export const LocalAiDecisionConfigSchema = z.object({
  project_key: z.string().min(1),
  endpoint_url: z.string().min(1),
  model_id: z.string().min(1),
  permission_scope: z.string().min(1),
  local_only_mode: z.boolean(),
});

export const LocalAiDecisionDocSchema = z.object({
  row: z.literal("111-UI"),
  decision_id: z.string().min(1),
  config: LocalAiDecisionConfigSchema,
});

export type LocalAiDecisionDoc = z.infer<typeof LocalAiDecisionDocSchema>;

export async function writeLocalAiDecisionDoc(
  projectKey: string,
  patch: Record<string, unknown>,
  statement: string,
  reason: string,
  authority: string,
): Promise<LocalAiDecisionDoc> {
  return requestJson(
    "/api/v1/app/local-ai/decision-update",
    {
      method: "POST",
      kind: "write",
      body: {
        project_key: projectKey,
        patch,
        statement,
        reason,
        authority,
      },
    },
    LocalAiDecisionDocSchema,
  );
}

// 111-UI read leg: the settings view over the stored config
// (src/agent_si/http/k07next5.py local_ai_view, quoting
// get_local_ai_view in src/agent_si/local/config.py).
export const LocalAiViewDocSchema = z.object({
  row: z.literal("111-UI"),
  project_key: z.string().min(1),
  title_key: z.string().min(1),
  purpose_key: z.string().min(1),
  need_it_now_key: z.string().min(1),
  config: LocalAiDecisionConfigSchema,
});

export type LocalAiViewDoc = z.infer<typeof LocalAiViewDocSchema>;

export async function readLocalAiViewDoc(
  projectKey: string,
): Promise<LocalAiViewDoc> {
  return requestJson(
    `/api/v1/app/local-ai/view?project_key=${encodeURIComponent(projectKey)}`,
    { method: "GET", kind: "read" },
    LocalAiViewDocSchema,
  );
}

// R-341-UI: the benchmark settings tab over the served bench tab
// route (src/agent_si/http/k07next5.py bench_tab, quoting scan_route,
// estimate_route, results_route, history_route plus check_route in
// src/agent_si/backend/localbench_routes.py and build_prestart_warnings
// in src/agent_si/local/bench_protocol.py).
export const BenchEstimateSchema = z.object({
  model_id: z.string().min(1),
  level: z.string().min(1),
  minutes_min: z.number(),
  minutes_max: z.number(),
});

export const BenchWarningSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
});

export const BenchTabDocSchema = z.object({
  row: z.literal("R-341-UI"),
  scan: z.array(z.string()),
  estimate: BenchEstimateSchema,
  warnings: z.array(BenchWarningSchema),
  results: z.array(z.unknown()),
  results_by_model: z.record(z.string(), z.array(z.unknown())),
  history: z.array(z.unknown()),
  gateway: z.unknown(),
});

export type BenchTabDoc = z.infer<typeof BenchTabDocSchema>;

export async function readBenchTabDoc(
  modelId: string,
  level: string,
  pcInUse: boolean,
): Promise<BenchTabDoc> {
  const query =
    `model_id=${encodeURIComponent(modelId)}` +
    `&level=${encodeURIComponent(level)}` +
    `&pc_in_use=${pcInUse ? "1" : "0"}`;
  return requestJson(
    `/api/v1/app/bench/tab?${query}`,
    { method: "GET", kind: "read" },
    BenchTabDocSchema,
  );
}

// B0B-UNCOVERED_ARCH-526: the stored Local AI config view over the
// served settings view route (src/agent_si/http/k07next5.py
// local_ai_settings_view, quoting get_local_ai_view in
// src/agent_si/local/config.py plus list_models in
// src/agent_si/backend/local_connect.py).
export const LocalAiSettingsViewDocSchema = z.object({
  row: z.literal("B0B-UNCOVERED_ARCH-526"),
  project_key: z.string().min(1),
  title_key: z.string().min(1),
  purpose_key: z.string().min(1),
  need_it_now_key: z.string().min(1),
  config: LocalAiDecisionConfigSchema,
  endpoint_url: z.string().min(1),
  models: z.array(z.unknown()),
});

export type LocalAiSettingsViewDoc = z.infer<
  typeof LocalAiSettingsViewDocSchema
>;

export async function readLocalAiSettingsViewDoc(
  projectKey: string,
): Promise<LocalAiSettingsViewDoc> {
  return requestJson(
    `/api/v1/app/local-ai/settings-view?project_key=${encodeURIComponent(projectKey)}`,
    { method: "GET", kind: "read" },
    LocalAiSettingsViewDocSchema,
  );
}

// B0B-UNCOVERED_MVP_ACCEPT-199: the outage fixture over the served
// provider health transitions route (src/agent_si/http/k07next5.py
// provider_health_transitions, quoting map_service_status in
// src/agent_si/budget/observe.py).
export const ProviderHealthTransitionRowSchema = z.object({
  registry: z.string().min(1),
  service: z.string().min(1),
  reason: z.string(),
});

export const ProviderHealthTransitionsDocSchema = z.object({
  row: z.literal("B0B-UNCOVERED_MVP_ACCEPT-199"),
  rows: z.array(ProviderHealthTransitionRowSchema),
  transitions: z.array(z.string().min(1)),
});

export type ProviderHealthTransitionsDoc = z.infer<
  typeof ProviderHealthTransitionsDocSchema
>;

export async function readProviderHealthTransitionsDoc(): Promise<ProviderHealthTransitionsDoc> {
  return requestJson(
    "/api/v1/app/provider-health/transitions",
    { method: "GET", kind: "read" },
    ProviderHealthTransitionsDocSchema,
  );
}
