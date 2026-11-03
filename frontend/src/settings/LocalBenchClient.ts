// K07C LocalBench settings sub-lane: HTTP client over the frozen K05 M3
// STEP1e routes. One function per reachable route (test_iface_m3.py:100-114:
// GET scan, GET estimate, POST runs, POST pause/resume/stop, GET results);
// reads are kind "read", writes are kind "write" with the UI token attached
// by requestJson/requestVoid.

import { z } from "zod";
import {
  BenchEstimateWireSchema,
  BenchRunIdSchema,
  LOCALBENCH_ENDPOINTS,
  LocalBenchResultRowsSchema,
  LocalBenchScanIdsSchema,
  expandBenchEstimate,
  expandBenchResults,
  expandBenchScan,
  fromWireLevel,
  toWireRunBody,
} from "./LocalBenchTypes";
import type {
  BenchmarkLevel,
  LocalBenchEstimate,
  LocalBenchModel,
  LocalBenchResultRow,
  LocalBenchRunRequest,
  LocalBenchScanResult,
} from "./LocalBenchTypes";
import { requestJson, requestVoid } from "../api/errors";
import { parseModelsPayload } from "./ProvidersPage/modelsApi";

// Wire: the R2 provider model route answers {provider_id, models,
// source, enabled}; the scan reads the served rows only.
const ProviderModelsWireSchema = z.object({
  models: z.array(z.unknown()),
});

export interface LocalBenchClient {
  scanModels(path: string): Promise<LocalBenchScanResult>;
  /** R5: scan the attached local runtime's real models (no folder).
  Optional: folder-only clients keep working. */
  scanRuntimeModels?(presetId: string): Promise<LocalBenchScanResult>;
  readEstimate(
    modelId: string,
    level: BenchmarkLevel,
  ): Promise<LocalBenchEstimate>;
  startRun(request: LocalBenchRunRequest): Promise<string>;
  pauseRun(runId: string): Promise<void>;
  resumeRun(runId: string): Promise<void>;
  stopRun(runId: string): Promise<void>;
  readResults(runId: string): Promise<LocalBenchResultRow[]>;
}

export async function scanLocalBenchModels(
  path: string,
): Promise<LocalBenchScanResult> {
  const ids = await requestJson(
    expandBenchScan(LOCALBENCH_ENDPOINTS.scan, path),
    { method: "GET", kind: "read" },
    LocalBenchScanIdsSchema,
  );
  // scan_route returns ids only (localbench_routes.py); the tier stays
  // UNKNOWN (M4: no evidence yet) until a run measures the model.
  return {
    path,
    models: ids.map(
      (model_id): LocalBenchModel => ({
        model_id,
        display_name: model_id,
        evidence: "UNKNOWN",
      }),
    ),
  };
}

export async function readLocalBenchEstimate(
  modelId: string,
  level: BenchmarkLevel,
): Promise<LocalBenchEstimate> {
  const wire = await requestJson(
    expandBenchEstimate(LOCALBENCH_ENDPOINTS.estimate, modelId, level),
    { method: "GET", kind: "read" },
    BenchEstimateWireSchema,
  );
  return {
    model_id: wire.model_id,
    level: fromWireLevel(wire.level),
    minutes_min: wire.minutes_min,
    minutes_max: wire.minutes_max,
  };
}

export async function startLocalBenchRun(
  request: LocalBenchRunRequest,
): Promise<string> {
  return requestJson(
    LOCALBENCH_ENDPOINTS.runs,
    { method: "POST", kind: "write", body: toWireRunBody(request) },
    BenchRunIdSchema,
  );
}

export async function pauseLocalBenchRun(runId: string): Promise<void> {
  await requestVoid(LOCALBENCH_ENDPOINTS.pause, {
    method: "POST",
    kind: "write",
    body: { run_id: runId },
  });
}

export async function resumeLocalBenchRun(runId: string): Promise<void> {
  await requestVoid(LOCALBENCH_ENDPOINTS.resume, {
    method: "POST",
    kind: "write",
    body: { run_id: runId },
  });
}

export async function stopLocalBenchRun(runId: string): Promise<void> {
  await requestVoid(LOCALBENCH_ENDPOINTS.stop, {
    method: "POST",
    kind: "write",
    body: { run_id: runId },
  });
}

export async function readLocalBenchResults(
  runId: string,
): Promise<LocalBenchResultRow[]> {
  return requestJson(
    expandBenchResults(LOCALBENCH_ENDPOINTS.results, runId),
    { method: "GET", kind: "read" },
    LocalBenchResultRowsSchema,
  );
}

// R5: scan one attached local runtime's real model names (no
// folder). Reads the provider model route the R2 lane serves for the
// preset (GET /api/v1/providers/{id}/models); the rows are the
// runtime's own listing, never placeholders.
export async function scanLocalBenchRuntimeModels(
  presetId: string,
): Promise<LocalBenchScanResult> {
  const data = await requestJson(
    `/api/v1/providers/${encodeURIComponent(presetId)}/models`,
    { method: "GET", kind: "read" },
    ProviderModelsWireSchema,
  );
  const outcome = parseModelsPayload(data, [], presetId);
  const rows = outcome?.rows ?? [];
  return {
    path: `runtime:${presetId}`,
    models: rows.map(
      (row): LocalBenchModel => ({
        model_id: row.id,
        display_name: row.label !== "" ? row.label : row.id,
        evidence: "UNKNOWN",
      }),
    ),
  };
}

export class HttpLocalBenchClient implements LocalBenchClient {
  scanModels(path: string): Promise<LocalBenchScanResult> {
    return scanLocalBenchModels(path);
  }

  scanRuntimeModels(presetId: string): Promise<LocalBenchScanResult> {
    return scanLocalBenchRuntimeModels(presetId);
  }

  readEstimate(
    modelId: string,
    level: BenchmarkLevel,
  ): Promise<LocalBenchEstimate> {
    return readLocalBenchEstimate(modelId, level);
  }

  startRun(request: LocalBenchRunRequest): Promise<string> {
    return startLocalBenchRun(request);
  }

  pauseRun(runId: string): Promise<void> {
    return pauseLocalBenchRun(runId);
  }

  resumeRun(runId: string): Promise<void> {
    return resumeLocalBenchRun(runId);
  }

  stopRun(runId: string): Promise<void> {
    return stopLocalBenchRun(runId);
  }

  readResults(runId: string): Promise<LocalBenchResultRow[]> {
    return readLocalBenchResults(runId);
  }
}
