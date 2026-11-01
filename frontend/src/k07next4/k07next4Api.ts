// K07NEXT4 readers over the served k07next4 backend routes.
// Each reader quotes the server-shaped schema of its backend route
// (src/agent_si/http/k07next4.py); only global fetch is ever replaced.
import { z } from "zod";
import { requestJson } from "../api/errors";

// LIVE0-08: the guarded session write over the served session write
// route (src/agent_si/http/k07next4.py session_write).
export const SessionWriteDocSchema = z.object({
  row: z.literal("LIVE0-08"),
  token_ok: z.literal(true),
  actor: z.string().min(1),
});

export type SessionWriteDoc = z.infer<typeof SessionWriteDocSchema>;

export async function writeSessionTokenDoc(): Promise<SessionWriteDoc> {
  return requestJson(
    "/api/v1/k07next4/session-write",
    { method: "POST", kind: "write", body: {} },
    SessionWriteDocSchema,
  );
}

// LIVE0B-01: the projects list plus Add Project over the served
// projects routes (src/agent_si/http/k07next4.py projects_list,
// projects_create).
export const K07Next4ProjectSchema = z.object({
  project_id: z.string().min(1),
  name: z.string().min(1),
  folder_ref: z.string().min(1),
});

export type K07Next4Project = z.infer<typeof K07Next4ProjectSchema>;

export const ProjectsDocSchema = z.object({
  row: z.literal("LIVE0B-01"),
  projects: z.array(K07Next4ProjectSchema),
});

export type ProjectsDoc = z.infer<typeof ProjectsDocSchema>;

export async function readProjectsDoc(): Promise<ProjectsDoc> {
  return requestJson(
    "/api/v1/k07next4/projects",
    { method: "GET", kind: "read" },
    ProjectsDocSchema,
  );
}

export async function createProjectsDoc(
  name: string,
  folderRef: string,
): Promise<K07Next4Project> {
  const created = await requestJson(
    "/api/v1/k07next4/projects",
    {
      method: "POST",
      kind: "write",
      body: { name, folder_ref: folderRef },
    },
    z.object({
      row: z.literal("LIVE0B-01"),
      project: K07Next4ProjectSchema,
    }),
  );
  return created.project;
}

// LIVE0B-04: the page shell over the served page shell route
// (src/agent_si/http/k07next4.py page_shell).
export const PageShellDocSchema = z.object({
  row: z.literal("LIVE0B-04"),
  title_key: z.string().min(1),
  title: z.string().min(1),
  console_class: z.string().min(1),
});

export type PageShellDoc = z.infer<typeof PageShellDocSchema>;

export async function readPageShellDoc(): Promise<PageShellDoc> {
  return requestJson(
    "/api/v1/k07next4/page-shell",
    { method: "GET", kind: "read" },
    PageShellDocSchema,
  );
}

// LIVE0B-05: the chat-started task over the served chat task route
// (src/agent_si/http/k07next4.py chat_task).
export const ChatTaskDocSchema = z.object({
  row: z.literal("LIVE0B-05"),
  task_id: z.string().min(1),
  prompt_ref: z.string().min(1),
  status: z.string().min(1),
});

export type ChatTaskDoc = z.infer<typeof ChatTaskDocSchema>;

export async function startChatTaskDoc(
  promptRef: string,
): Promise<ChatTaskDoc> {
  return requestJson(
    "/api/v1/k07next4/chat-task",
    { method: "POST", kind: "write", body: { prompt_ref: promptRef } },
    ChatTaskDocSchema,
  );
}

// MH-5: the single step turn over the served step turn route
// (src/agent_si/http/k07next4.py step_turn).
export const StepTurnDocSchema = z.object({
  row: z.literal("MH-5"),
  turn: z.number().int().min(1),
  model_input: z.string().min(1),
  action: z.string().min(1),
  observation: z.string().min(1),
});

export type StepTurnDoc = z.infer<typeof StepTurnDocSchema>;

export async function readStepTurnDoc(
  advance: number,
): Promise<StepTurnDoc> {
  return requestJson(
    `/api/v1/k07next4/step-turn?advance=${encodeURIComponent(String(advance))}`,
    { method: "GET", kind: "read" },
    StepTurnDocSchema,
  );
}

// MH-6: the stored turn triple plus budget counter over the served
// turn triple route (src/agent_si/http/k07next4.py turn_triple).
// Shapes mirror TurnTripleSchema plus TaskTurnsSchema in
// frontend/src/api/projectsApi.ts.
export const TurnTripleDocSchema = z.object({
  row: z.literal("MH-6"),
  turns: z.array(
    z.object({
      plan: z.string().min(1),
      action: z.string().min(1),
      observation: z.string().min(1),
    }),
  ),
  used: z.number().int().min(0),
  limit: z.number().int().min(0),
});

export type TurnTripleDoc = z.infer<typeof TurnTripleDocSchema>;

export async function readTurnTripleDoc(): Promise<TurnTripleDoc> {
  return requestJson(
    "/api/v1/k07next4/turn-triple",
    { method: "GET", kind: "read" },
    TurnTripleDocSchema,
  );
}
