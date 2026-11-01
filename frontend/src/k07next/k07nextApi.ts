// K07NEXT split B: read functions over the served k07next boundary.
// Each reader quotes the server-shaped schema of its backend route
// (src/agent_si/http/k07next.py); only global fetch is ever replaced.
import { z } from "zod";
import { requestJson } from "../api/errors";

export const K07NEXT_BASE = "/api/v1/app";

export const NewcomerGuideSchema = z.object({
  row: z.literal("R-319"),
  guide: z.literal("newcomer_start_guide"),
  steps: z.array(z.object({ id: z.string().min(1) })),
});

export type NewcomerGuideDoc = z.infer<typeof NewcomerGuideSchema>;

export async function readNewcomerGuide(): Promise<NewcomerGuideDoc> {
  return requestJson(
    `${K07NEXT_BASE}/newcomer-guide`,
    { method: "GET", kind: "read" },
    NewcomerGuideSchema,
  );
}

export const LocaleSwitchSchema = z.object({
  row: z.literal("R-334"),
  locales: z.array(z.string().min(1)),
  visible_switch: z.object({
    top_bar: z.boolean(),
    settings: z.boolean(),
  }),
  persisted_via: z.string().min(1),
});

export type LocaleSwitchDoc = z.infer<typeof LocaleSwitchSchema>;

export async function readLocaleSwitch(): Promise<LocaleSwitchDoc> {
  return requestJson(
    `${K07NEXT_BASE}/locale-switch`,
    { method: "GET", kind: "read" },
    LocaleSwitchSchema,
  );
}

export const LicenceSchema = z.object({
  row: z.literal("R-342"),
  licence_line: z.string().min(1),
  mit_ref: z.string().min(1),
  third_party_title_ref: z.string().min(1),
});

export type LicenceDoc = z.infer<typeof LicenceSchema>;

export async function readLicence(): Promise<LicenceDoc> {
  return requestJson(
    `${K07NEXT_BASE}/licence`,
    { method: "GET", kind: "read" },
    LicenceSchema,
  );
}

export const RunsExplainedSchema = z.object({
  row: z.literal("R-348"),
  sections: z.array(z.object({ key: z.string().min(1) })),
});

export type RunsExplainedDoc = z.infer<typeof RunsExplainedSchema>;

export async function readRunsExplained(): Promise<RunsExplainedDoc> {
  return requestJson(
    `${K07NEXT_BASE}/runs-explained`,
    { method: "GET", kind: "read" },
    RunsExplainedSchema,
  );
}

export const LocaleCoverageSchema = z.object({
  row: z.literal("R-362"),
  en_leaves: z.number(),
  uk_leaves: z.number(),
  parity: z.boolean(),
  missing_in_uk: z.array(z.string()),
  missing_in_en: z.array(z.string()),
});

export type LocaleCoverageDoc = z.infer<typeof LocaleCoverageSchema>;

export async function readLocaleCoverage(): Promise<LocaleCoverageDoc> {
  return requestJson(
    `${K07NEXT_BASE}/locale-coverage`,
    { method: "GET", kind: "read" },
    LocaleCoverageSchema,
  );
}

export const TelemetryThemesSchema = z.object({
  row: z.literal("M-P3-92"),
  themes: z.array(z.string().min(1)),
  charts: z.string().min(1),
  standard: z.string().min(1),
  tokens_key: z.string().min(1),
  cost_key: z.string().min(1),
});

export type TelemetryThemesDoc = z.infer<typeof TelemetryThemesSchema>;

export async function readTelemetryThemes(): Promise<TelemetryThemesDoc> {
  return requestJson(
    `${K07NEXT_BASE}/telemetry-themes`,
    { method: "GET", kind: "read" },
    TelemetryThemesSchema,
  );
}

export const CopyrightSchema = z.object({
  row: z.literal("M-P4-139"),
  line_en: z.string().min(1),
  line_uk: z.string().min(1),
  shown_in: z.array(z.string().min(1)),
});

export type CopyrightDoc = z.infer<typeof CopyrightSchema>;

export async function readCopyright(): Promise<CopyrightDoc> {
  return requestJson(
    `${K07NEXT_BASE}/copyright`,
    { method: "GET", kind: "read" },
    CopyrightSchema,
  );
}
