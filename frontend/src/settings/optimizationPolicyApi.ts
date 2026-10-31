// ARCH-528 Optimization Policy view helper: real GET over the served
// /api/v1/routing/optimization-policy shape (required quality, risk
// ceiling, weights). Reads are open (kind "read", no session token).
// No frozen api/* file is touched.

import { z } from "zod";
import { requestJson } from "../api/errors";

const OptimizationWeightsSchema = z.object({
  weight_quality: z.number(),
  weight_cost: z.number(),
  weight_latency: z.number(),
  weight_cloud_tokens: z.number(),
});

export type OptimizationWeights = z.infer<typeof OptimizationWeightsSchema>;

const OptimizationPolicySchema = z.object({
  policy_id: z.string().min(1),
  version: z.number().int(),
  required_quality: z.number(),
  max_risk: z.string().min(1),
  weights: OptimizationWeightsSchema,
  local_preference: z.boolean(),
});

export type OptimizationPolicy = z.infer<typeof OptimizationPolicySchema>;

export function optimizationPolicyPath(): string {
  return "/api/v1/routing/optimization-policy";
}

export async function readOptimizationPolicy(): Promise<OptimizationPolicy> {
  return requestJson(
    optimizationPolicyPath(),
    { method: "GET", kind: "read" },
    OptimizationPolicySchema,
  );
}
