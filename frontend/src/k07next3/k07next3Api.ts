// K07NEXT3 split B: read functions over already-served backend routes.
// Each reader quotes the server-shaped schema of its backend route
// (src/agent_si/backend/*.py); only global fetch is ever replaced.
import { z } from "zod";
import { requestJson } from "../api/errors";

// B0B-UNCOVERED_MVP_ACCEPT-178: the live agents payload over the served
// agents live route (src/agent_si/backend/app.py:125 agents_live).
export const AgentsLiveDocSchema = z.object({
  agents: z.array(
    z.object({
      agent: z.string(),
      scope: z.string(),
      deliverable: z.string(),
      status: z.string(),
    }),
  ),
});

export type AgentsLiveDoc = z.infer<typeof AgentsLiveDocSchema>;

export async function readAgentsLiveDoc(): Promise<AgentsLiveDoc> {
  return requestJson(
    "/api/v1/agents/live",
    { method: "GET", kind: "read" },
    AgentsLiveDocSchema,
  );
}

// B0B-UNCOVERED_MVP_ACCEPT-199: the bench scan listing over the served
// bench scan route (src/agent_si/backend/localbench_routes.py:195).
export const BenchScanDocSchema = z.array(z.string());

export type BenchScanDoc = z.infer<typeof BenchScanDocSchema>;

export async function readBenchScanDoc(): Promise<BenchScanDoc> {
  return requestJson(
    "/api/v1/local/bench/scan",
    { method: "GET", kind: "read" },
    BenchScanDocSchema,
  );
}

// LIVE0-02: the bench run estimate over the served bench estimate route
// (src/agent_si/backend/localbench_routes.py:206 estimate).
export const BenchEstimateDocSchema = z.object({
  level: z.string().min(1),
  model_id: z.string().min(1),
  minutes_min: z.number().min(0),
  minutes_max: z.number().min(0),
});

export type BenchEstimateDoc = z.infer<typeof BenchEstimateDocSchema>;

export async function readBenchEstimateDoc(
  modelId: string,
): Promise<BenchEstimateDoc> {
  return requestJson(
    `/api/v1/local/bench/estimate?model_id=${encodeURIComponent(modelId)}&level=Quick`,
    { method: "GET", kind: "read" },
    BenchEstimateDocSchema,
  );
}

// LIVE0-03: the known bench run ids over the served bench history route
// (src/agent_si/backend/localbench_routes.py:219 history).
export const BenchHistoryDocSchema = z.array(z.string());

export type BenchHistoryDoc = z.infer<typeof BenchHistoryDocSchema>;

export async function readBenchHistoryDoc(): Promise<BenchHistoryDoc> {
  return requestJson(
    "/api/v1/local/bench/history",
    { method: "GET", kind: "read" },
    BenchHistoryDocSchema,
  );
}

// LIVE0-05: the tests view board over the served tests view route
// (src/agent_si/backend/read_routes.py:283 tests view).
export const TestsViewDocSchema = z.object({
  plan_id: z.string().min(1),
  run_id: z.string().min(1),
  active: z.number().int().min(0),
  passed: z.number().int().min(0),
  remaining: z.number().int().min(0),
  rows: z.array(
    z.object({
      test_id: z.string().min(1),
      status: z.string().min(1),
      output_ref: z.string().nullable(),
    }),
  ),
  settings_controls: z.array(z.string()),
});

export type TestsViewDoc = z.infer<typeof TestsViewDocSchema>;

export async function readTestsViewDoc(
  planId: string,
  runId: string,
): Promise<TestsViewDoc> {
  return requestJson(
    `/api/v1/teststage/tests-view?plan_id=${encodeURIComponent(planId)}&run_id=${encodeURIComponent(runId)}`,
    { method: "GET", kind: "read" },
    TestsViewDocSchema,
  );
}
