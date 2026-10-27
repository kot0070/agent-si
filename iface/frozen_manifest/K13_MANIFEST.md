# K13 FROZEN INTERFACE MANIFEST (Day 0, DRAFT)

status: DRAFT (does not self-freeze; frozen only after 0F PASS) | step: 0E pre-lane E1 | owner: K13
 Naming authority: RECORDS/day0/0C_ARCHITECTURE.md (0C wins every clash; conflicts in reconciliation table, else "none").
 Frozen after 0F PASS: later changes only as a named delta (K13-DELTA-n) with supersedes ref; all Day-1 packages build against this text from hour one.
 Holding files: kit/BUILD_PLAN.md:369-423 (engine spine), kit/BUILD_PLAN.md:1146-1239 (spec map), kit/BUILD_PLAN.md:1421-1470 (coverage rows), kit/DEV_HANDBOOK.md:91-126 (composition root, guard), RECORDS/day0/0C_ARCHITECTURE.md (names).
 Probe note: exact record field names agent_task_id and parent_task_id contain the workspace-path probe substring; a naive substring probe false-positives on them. Gate probes use the path form with a trailing separator.

## Conventions (apply to every record below)

- id shape: stable string ids (project_id, task_id, run_id, attempt_id, ...); sequences monotonic per scope, atomically allocated, UNIQUE(scope, sequence).
- version+hash rule: immutable records carry (version, hash); hash over canonical field order; new content = new version, never rewrite. Mutable aggregates recompute derived state; policy lifecycle lives in PolicyLifecycleRecord, never in a status field on the policy.
- concurrency: compare-and-set on (id, expected_version); loser re-reads; timestamps never arbitrate.
- refs: every record carries project_id; task/run links where applicable; created_at/updated_at where applicable; referential integrity enforced at write.
- ARTIFACT_REF beats repeated inline content (large context travels by ref + hash).

## Record inventory (K13-owned schemas; writers per handoff section)

### §0 SYSTEM_GOAL

K13 owns the headless engine chain records: Project -> Task -> TaskContract -> ExecutionRun -> ExecutionAttempt -> VerificationRecord -> AuditRecord -> FinalizationRecord -> TelemetryEvent + MetricRecord -> report dataset.
 TARGET_FLOW chain: Project, user task, Director (control plane only), Manager, Manager agents, TaskPlanner, TaskRouter, ModelRouter, AttemptExecutionGate, LOCAL/SPLIT/CLOUD worker, deterministic verification, independent audit, bounded correction loop, Finalizer, runtime telemetry, project analytics. cite: kit/PRODUCT_SPEC.md:170-206.
 Core accounting ALWAYS_ON; models never source totals (tokens, time, usage, retries, rework, history, cost). cite: kit/PRODUCT_SPEC.md:195-197.
 Default operational Manager provider/model: meta / meta/muse-spark-1.3-contributor (shipped preset, user-changeable; never hard-coded in code paths). cite: kit/PRODUCT_SPEC.md:206, 0C sec 3.

### §1 AUTHORITY

Runtime authority order: USER > DIRECTOR > MANAGER > AGENTS. cite: kit/PRODUCT_SPEC.md:210-213.
 Auditor commands nothing; controls PASS eligibility. No REWORK/BLOCKED/ESCALATE/FAIL -> PASS conversion without new independent evidence or audit. cite: kit/PRODUCT_SPEC.md:215-225.
 Only the user authors/activates/supersedes an OverridePolicy (with NON_OVERRIDABLE lists); override never creates PASS, never rewrites evidence, never bypasses NON_OVERRIDABLE gates. cite: kit/PRODUCT_SPEC.md:224.
 K13 interfaces: OverridePolicy ref check on every accepted-risk edge (§18B); AuthorizationRecord refs for R2/R3 edges (handoff section).

### §3A MANAGER

Manager = bounded TaskPackage in, execution out: runs planner/router, fans out one worker task per worker (bounded by scheduler + retry policy), collects outputs as ArtifactRefs, requests verification + independent audit, handles bounded correction/fallback, returns MANAGER_RETURN (K02-owned record, referenced here by name only).
 Manager never: audits own work, expands scope, changes TaskContract outside Director amendments, bypasses gates, receives raw secrets. cite: kit/PRODUCT_SPEC.md:274-290.
 K13 interfaces consumed: TaskPackage/AgentTask schemas (§21A), AttemptExecutionGate (§17C), ArtifactRef (§40), SecretRef rule (§20A).

### §3A.MANAGER_OPERATIONS

Same rules in operational form: artifact refs, bounded rework/fallback, manager-return record, gate + authorization checks, no raw secrets. cite: kit/PRODUCT_SPEC.md:274-290, 0C sec 4.
 K13 interfaces: POLICY_REF_VALIDATION gate (§21A), CONTEXT_WRONG_CONTRACT_VERSION / POLICY_CONFLICT / CONTEXT_MISSING errors (names frozen here, owner K13).

### §3B DEFAULT_MANAGER_PROFILE

DefaultManagerProfile: profile_id (id shape DMP-001), version: int, provider: string, model: string, binding: ManagerProfileBinding, hash: string. cite: kit/PRODUCT_SPEC.md:297-304.
 ENUM ManagerProfileBinding: DEFAULT | HARD_LOCK. cite: kit/PRODUCT_SPEC.md:306-308.
 Rules frozen: DEFAULT is not a hard lock; every Manager bootstrap binds the project default; a different Manager model only via recorded FallbackRecord, routing/policy DecisionRecord, or explicit user override persisted as RoutingDecision/FallbackRecord with provenance + TelemetryEvent; profile change = new version + DecisionRecord. cite: kit/PRODUCT_SPEC.md:310-320.

### §3B.RECORD

Same record as §3B (fields above); bootstrap binds project default; no per-run re-selection outside the triggers above; actual Manager identity from execution provenance joins audit implementer sets where it contributes. cite: kit/PRODUCT_SPEC.md:310-320.

### §6 PRE_IMPLEMENTATION_POLICY

Code-first on the OpenAI Agents SDK via OrchestrationInterface + OpenAIAgentsSDKAdapter; Agent Builder never a runtime dependency (imported workflow = untrusted input until revalidated). cite: kit/PRODUCT_SPEC.md:416-428.
 No product implementation before 0F PASS. cite: kit/PRODUCT_SPEC.md:433-440.
 K13 interfaces: OrchestrationInterface, OpenAIAgentsSDKAdapter (§43); SDK capability verification is a Phase-0 input, not a manifest record.

### §8 PRODUCT_PROJECT_MODEL

Project: project_id, name, description, created_at, updated_at, status, workspace_root, default_director, default_manager_provider, default_manager_model, default_policies, budget_config, local_ai_config_ref, capability_db_ref, core_accounting (=ALWAYS_ON const), diagnostic_telemetry_enabled: bool, sdk_tracing_enabled: bool, archived: bool. cite: kit/PRODUCT_SPEC.md:491-533.
 id shape: project_id stable string. version+hash: mutable config; profile/policy changes version via DecisionRecord (§3B).
 Every task, run, event carries project_id. cite: kit/PRODUCT_SPEC.md:491-533, 0C sec 3.
 RoleModelProfile (0C-sourced, frozen here): role, project_id, mode: PINNED|pool|AUTO, provider, model, binding, version, hash. One row per executable role per project; user-changeable config seeded with shipped preset. cite: 0C sec 3.

### §9 APPLICATION_NATIVE_TELEMETRY

Core accounting ALWAYS_ON. Diagnostic telemetry and SDK tracing switch independently by policy. cite: kit/PRODUCT_SPEC.md:534-540.
 Source priority (frozen order): provider/runtime API > Agents SDK + runtime instrumentation > application orchestration runtime > monotonic/system clock > local provider metrics > deterministic application calculation > explicit estimation > UNAVAILABLE. cite: kit/PRODUCT_SPEC.md:542-551.
 AI-written prose is never telemetry evidence. cite: kit/PRODUCT_SPEC.md:553.
 K13 interfaces: TelemetryEvent envelope + MetricRecord (§55, §11); CostCalculator over PricingSnapshot (§11).

### §10 PROJECT_METRICS

Per-project aggregates (derived views over stored telemetry, never hand-written):
 PROJECT_TIME: created_at, first_run_at, last_run_at, active_wall_time, AI_execution_time, Manager_time, Agent_time, verification_time, audit_time, correction_time, waiting_time.
 AI_USAGE: total_calls, cloud_calls, local_calls, split_runs, provider_calls, model_calls.
 TOKENS: cloud_input_tokens, cloud_output_tokens, cached_tokens, billable_tokens, tokens_by_provider, tokens_by_model, tokens_by_role, tokens_by_task, tokens_by_run.
 LOCAL_AI: local_calls, local_execution_time, models_used, provider_instances, local_failures, local_fallbacks.
 CLOUD_AI: cloud_calls, providers_used, models_used, cloud_execution_time, tokens, cost.
 QUALITY: tasks_pass, tasks_correction, tasks_failed, audit_pass, audit_correction, verification_failures.
 SYSTEM: retries, fallbacks, errors, incidents, workspace_violations. cite: kit/PRODUCT_SPEC.md:555-622.
 K13 interfaces: MetricRecord rows per aggregate cell (§11); report dataset builder (§59).

### §11 METRIC_SEMANTICS

PricingSnapshot: pricing_snapshot_id, provider_id, model_id, currency, effective_at, source, input_token_price|null, output_token_price|null, cached_token_price|null, reasoning_token_price|null, request_price|null, other_rules[], created_at, hash. cite: kit/PRODUCT_SPEC.md:625-643.
 Rules: authoritative when used for calculated cost; MetricRecord references snapshot for calculated cost; historical cost reproduces from original snapshot; corrections = new snapshot version. cite: kit/PRODUCT_SPEC.md:644-648.
 ENUM MetricState: MEASURED | CALCULATED | ESTIMATED | INFERRED | UNAVAILABLE. cite: kit/PRODUCT_SPEC.md:649-655.
 MetricRecord: metric_id, project_id, task_id, run_id, metric_name, value, unit, state: MetricState, source (REQUIRED, canonical provenance field), recorded_at. cite: kit/PRODUCT_SPEC.md:657-671.
 Rules: value+unit+state+source required at write; cost only via CostCalculator over PricingSnapshot; never fabricate; re-collection with identical usage ref attaches without duplicating measured totals. cite: kit/PRODUCT_SPEC.md:672-687.
 id shape: metric_id stable string. version+hash: immutable, append-only; corrections are new records.

### §11A TIME_ACCOUNTING_SEMANTICS

ACTIVE_WALL_TIME = union of active execution intervals (parallel counts once; never a role-time sum). AI_EXECUTION_TIME additive. ROLE_EXECUTION_TIME grouped by role. WAITING_TIME measured non-executing waits. cite: kit/PRODUCT_SPEC.md:688-706.
 Every time metric carries state + source. cite: kit/PRODUCT_SPEC.md:702-706.
 K13 interfaces: MetricRecord rows with metric_name in {active_wall_time, ai_execution_time, role_execution_time, waiting_time}.

### §12 TASK_STATE_MACHINE

ENUM TaskState: CREATED | PACKAGED | ASSIGNED | PLANNING | EXECUTING | VERIFYING | AUDITING | REWORK_PENDING | BLOCKED | ESCALATED | FAILED | CANCELLED | COMPLETED. cite: kit/PRODUCT_SPEC.md:832-846.
 ALLOWED (from -> event -> to; reason recorded per edge):
 CREATED -> allocate -> PACKAGED | cancel -> CANCELLED | fail -> FAILED.
 PACKAGED -> assign -> ASSIGNED | BLOCKED | CANCELLED.
 ASSIGNED -> plan -> PLANNING | BLOCKED | FAILED | CANCELLED.
 PLANNING -> execute -> EXECUTING | BLOCKED | ESCALATED | CANCELLED.
 EXECUTING -> verify -> VERIFYING | restart/reroute (AMENDMENT_RESTART, FALLBACK_REROUTE, EXECUTION_RETRY) -> REWORK_PENDING | BLOCKED | FAILED | ESCALATED | CANCELLED.
 VERIFYING -> audit -> AUDITING | retry loop (EXECUTION_RETRY) -> REWORK_PENDING | correction (VERIFICATION_REWORK) -> REWORK_PENDING | BLOCKED (suspended_from_state=VERIFYING, resume_target_state=VERIFYING) | FAILED | ESCALATED | CANCELLED.
 AUDITING -> audit disposition map -> COMPLETED | REWORK_PENDING | BLOCKED | ESCALATED | FAILED | CANCELLED.
 REWORK_PENDING -> EXECUTING | ESCALATED | CANCELLED (conditional accepted-risk -> COMPLETED only with user OverrideRecord, see override edges).
 BLOCKED -> previous_resumable_state | ESCALATED | CANCELLED (conditional accepted-risk -> COMPLETED only with user OverrideRecord).
 ESCALATED -> previous_resumable_state | FAILED | CANCELLED (conditional accepted-risk -> COMPLETED only with user OverrideRecord). cite: kit/PRODUCT_SPEC.md:848-859.
 TERMINAL: COMPLETED | FAILED | CANCELLED. ESCALATED = NON_TERMINAL_SUSPENDED. cite: kit/PRODUCT_SPEC.md:861-866.
 AUDIT_RESULT_TRANSITION_MAP (AUDITING ->): PASS -> COMPLETED; REWORK -> REWORK_PENDING; BLOCKED -> BLOCKED; ESCALATE -> ESCALATED; FAIL -> FAILED. cite: kit/PRODUCT_SPEC.md:868-874.
 CONDITIONAL_USER_OVERRIDE_EDGES (only canonical exceptions): REWORK_PENDING -> COMPLETED, BLOCKED -> COMPLETED, ESCALATED -> COMPLETED, each ONLY with explicit user authorization + CompletionDisposition=ACCEPTED_RISK + required OverrideRecord, AuditResult unchanged; FAIL never converts (recovery = new superseding Task). cite: kit/PRODUCT_SPEC.md:876-888.
 FORBIDDEN (no edge, no bypass): silent transition; self-PASS; audit bypass; EXECUTING -> COMPLETED; VERIFYING -> COMPLETED. cite: kit/PRODUCT_SPEC.md:922-923.
 Restart/reroute rule: AMENDMENT_RESTART | FALLBACK_REROUTE move EXECUTING/VERIFYING/AUDITING -> REWORK_PENDING with correction count NOT incremented; next legal edge REWORK_PENDING -> EXECUTING with a new bound ExecutionRun. ENUM RestartReason: AMENDMENT_RESTART | FALLBACK_REROUTE. cite: kit/PRODUCT_SPEC.md:709-726.
 Transition record: transition_id, project_id, task_id, run_id|null, transition_sequence (monotonic per task_id, atomic, UNIQUE(task_id, transition_sequence)), expected_from_state, expected_state_version, new_state_version (UNIQUE(task_id, new_state_version)), actor, from, to, reason, timestamp, evidence_ref, suspended_from_state, resume_target_state. cite: kit/PRODUCT_SPEC.md:890-907.
 CAS rule: commit iff current_state == expected_from_state == from AND current_state_version == expected_state_version; atomic write of record + current_state + new version; stale commits fail and re-read; timestamps never arbitrate; recovery derives latest state from highest committed state_version/sequence. cite: kit/PRODUCT_SPEC.md:909-920.
 RESUME_INVARIANT: entering BLOCKED/ESCALATED captures concrete suspended_from_state; resume_target_state concrete, recorded, legal, same-contract-preserving, never model-inferred; resume targets it unless a DecisionRecord/Amendment changes it. cite: kit/PRODUCT_SPEC.md:824-830.
 Suspension runtime rule (§12 part): on BLOCKED/ESCALATED with live work: halt new attempts + side effects, mark suspended, cancel/interrupt provider calls where supported (uncancellable results quarantined LATE_AFTER_SUSPENSION, never auto-resume), runs hold SUSPENDED_BY_TASK, release leases/reservations and unused budget coverage unless policy holds them bounded, committed side effects stay authoritative; resume requires ContextRecoveryCheck + AttemptExecutionGate + ownership/budget/authorization revalidation; cancelled/finished attempts never reopened. cite: kit/PRODUCT_SPEC.md:767-786.
 SuspensionRecord: suspension_id, project_id, task_id, run_id|null, attempt_id|null, source_task_state, reason, started_at, resolved_at|null, run_suspension_state: RunSuspensionState, late_result_disposition: AttemptResultDisposition|null, evidence_refs[], status. ENUM RunSuspensionState: NONE | SUSPENDED_BY_TASK. ENUM AttemptResultDisposition: NORMAL | LATE_AFTER_SUSPENSION | QUARANTINED | RECONCILED_ACCEPTED | RECONCILED_REJECTED. Authoritative + persistent; quarantine survives restart. cite: kit/PRODUCT_SPEC.md:737-765.
 LateResultReconciliationRecord: reconciliation_id, project_id, task_id, run_id, attempt_id, suspension_id, late_output_refs[], decision: LateResultDecision, decided_by, decided_at, reason, verification_ref|null, evidence_refs[]. ENUM LateResultDecision: ACCEPT_AS_EVIDENCE | REJECT | SUPERSEDED. Rules: Director/authorized recovery controller only; never auto-resume; ACCEPT_AS_EVIDENCE needs compatible contract_hash + no superseding output + completed verification + policy pass; never reopens terminal attempts/tasks. cite: kit/PRODUCT_SPEC.md:790-822.

### §13 TASK_CONTRACT

TaskContract: schema_version, contract_version, contract_sequence (monotonic per task_id; UNIQUE(task_id, contract_version); UNIQUE(task_id, contract_sequence)), contract_hash, project_id, task_id, parent_task_id, supersedes_task_id, phase_id, created_at, created_by, priority, risk: RiskLevel, goal, requirements[], acceptance_criteria[], inputs[], outputs[], workspace, permissions, tools[], verification_policy_ref, audit_policy_ref, routing_policy_ref, retry_policy_ref, fallback_policy_ref, optimization_policy_ref, override_policy_ref. cite: kit/PRODUCT_SPEC.md:928-958.
 Rules: old contract immutable; requirement change = new version + hash; active ONLY via committed ContractActivationRecord; active = highest committed activation_sequence per task_id; never infer from file order/timestamp/model memory; auditor checks exact contract_hash used. cite: kit/PRODUCT_SPEC.md:959-969.
 id shape: (task_id, contract_version). version+hash: contract_hash over canonical contract content; activation-gated.

### §13A ACCEPTANCE_CRITERION

AcceptanceCriterion: ac_id, statement, source, type: ACType, required: bool, severity: FailureSeverity, verification_method, verifier_ref, evidence_required: bool, pass_condition. cite: kit/PRODUCT_SPEC.md:973-984.
 ENUM ACType: DETERMINISTIC | SEMANTIC | SECURITY | ARCHITECTURE | MANUAL. cite: kit/PRODUCT_SPEC.md:986-991.
 Rules: deterministic criteria via DeterministicVerify; semantic/architecture/security/manual via independent verification/audit; PASS needs explicit result per required criterion + evidence where required. cite: kit/PRODUCT_SPEC.md:993-998.
 id shape: ac_id stable per contract version (new contract version = new criterion set).

### §14 EXECUTION_RUN

ENUM ExecutionRunCreationReason: INITIAL_EXECUTION | VERIFICATION_REWORK | AUDIT_REWORK | AMENDMENT_RESTART | FALLBACK_REROUTE. cite: kit/PRODUCT_SPEC.md:1002-1007.
 ExecutionRun: run_id, project_id, task_id, contract_hash (exactly one per run lifetime), run_sequence (monotonic per task_id, atomic, UNIQUE(task_id, run_sequence)), revision_no (counts verification/audit correction loops only; amendment restart / fallback reroute do NOT increment), creation_reason: ExecutionRunCreationReason, source_run_id|null, routing_decision_ref|null, routing_decision_refs[], route|null, split_strategy|null, primary_provider|null, primary_provider_instance|null, primary_model|null, implementer_provider_ids[], implementer_model_ids[], status: ExecutionRunStatus, termination_reason: RunTerminationReason, started_at|null, ended_at|null, created_at. cite: kit/PRODUCT_SPEC.md:1009-1041, R66.
 Name note: 0C glossary + R66 fix the counter field as revision_no; the §14 body text token correction_no denotes the same counter. 0C wins.
 Rules: selection/routing fields nullable while CREATED; terminal historical fields immutable. cite: kit/PRODUCT_SPEC.md:1034-1041.
 Creation order (frozen transaction, no execution before step 13 passes): resolve active contract -> allocate run_sequence -> skeleton (CREATED, NONE, active hash, nulls) -> ModelRouter candidates -> scheduler precheck (no reserve) -> budget precheck -> persist RoutingEvidenceSnapshot -> persist RoutingDecision + assignments -> bind routing fields -> scheduler reserve -> budget reserve (token-denominated hard budget when price UNAVAILABLE) -> compensate on later-gate failure -> AttemptExecutionGate for initial attempt -> CREATED to RUNNING + started_at + first attempt; else PRE_RUN_FAILURE_DISPOSITION. cite: kit/PRODUCT_SPEC.md:1051-1072.
 Pre-run failure disposition (CREATED, cannot start): fallback/replacement decision BEFORE terminalization (FAILED never to SUPERSEDED); replacement run -> current CREATED to SUPERSEDED_BY_FALLBACK + rebind/clean; else FAILED with canonical reason + Task disposition: ROUTING_NO_ELIGIBLE_CANDIDATE -> Task ESCALATED; CAPABILITY_UNAVAILABLE -> Task ESCALATED; RESOURCE_FAILURE -> release, Task BLOCKED (recoverable) else ESCALATED; BUDGET_BLOCKED -> release reservation, Task BLOCKED (top-up/authorization possible) else ESCALATED; POLICY_BLOCK -> fallback if alternate compliant path, Task BLOCKED (recoverable) / ESCALATED (conflict) / FAILED (terminally unsatisfiable); correction-staging special case preserves failure class; no automatic retry without cause change or eligible fallback; leases/reservations/settlements for never-RUNNING runs released/settled/expired deterministically. cite: kit/PRODUCT_SPEC.md:1074-1109.
 id shape: run_id stable string. version+hash: run_sequence + immutable history; stored status consistent with attempt + verification + audit history.

### §14A EXECUTION_LIFECYCLE_ENUMS

Run audit disposition (status AUDITING): PASS -> SUCCEEDED + COMPLETED; REWORK -> REWORK_REQUIRED, replacement run created, prior run to SUPERSEDED_BY_REWORK; FAIL -> FAILED + AUDIT_FAIL; BLOCKED -> run holds AUDITING/SUSPENDED_BY_TASK, Task to BLOCKED (suspended_from_state=AUDITING, resume_target_state=AUDITING), no run mutation until resume/cancel/fail; ESCALATE -> same with ESCALATED. BLOCKED/ESCALATE are Task-level suspensions, never run-terminal. cite: kit/PRODUCT_SPEC.md:1113-1128.
 Run ALLOWED: CREATED -> RUNNING|FAILED|CANCELLED|SUPERSEDED; RUNNING -> VERIFYING|FAILED|CANCELLED|SUPERSEDED; VERIFYING -> RUNNING|AUDITING|REWORK_REQUIRED|FAILED|CANCELLED|SUPERSEDED; AUDITING -> SUCCEEDED|REWORK_REQUIRED|FAILED|CANCELLED|SUPERSEDED; REWORK_REQUIRED -> SUPERSEDED|CANCELLED. cite: kit/PRODUCT_SPEC.md:1130-1136.
 Run TERMINAL: SUCCEEDED | FAILED | CANCELLED | SUPERSEDED. Invariants: append-only history; REWORK_REQUIRED never returns to RUNNING in-run (new run); SUCCEEDED needs required verification + audit disposition; CANCELLED/FAILED need canonical reason; material fallback terminalizes/supersedes prior run per policy. cite: kit/PRODUCT_SPEC.md:1138-1152.
 ENUM ExecutionAttemptStatus: CREATED | RUNNING | SUCCEEDED | FAILED | CANCELLED. cite: kit/PRODUCT_SPEC.md:1154-1160.
 ENUM ExecutionRunStatus: CREATED | RUNNING | VERIFYING | AUDITING | REWORK_REQUIRED | SUCCEEDED | FAILED | CANCELLED | SUPERSEDED. cite: kit/PRODUCT_SPEC.md:1162-1172.
 ENUM RunTerminationReason: NONE | COMPLETED | EXECUTION_FAILED | VERIFICATION_FAILED | AUDIT_FAIL | CANCELLED_BY_USER | CANCELLED_BY_AMENDMENT | SUPERSEDED_BY_FALLBACK | SUPERSEDED_BY_REWORK | POLICY_BLOCK | RESOURCE_FAILURE | ROUTING_NO_ELIGIBLE_CANDIDATE | CAPABILITY_UNAVAILABLE | BUDGET_BLOCKED. cite: kit/PRODUCT_SPEC.md:1174-1189.
 RUN_STATUS_TERMINATION_COMPATIBILITY: SUCCEEDED -> COMPLETED; FAILED -> EXECUTION_FAILED|VERIFICATION_FAILED|AUDIT_FAIL|POLICY_BLOCK|RESOURCE_FAILURE|ROUTING_NO_ELIGIBLE_CANDIDATE|CAPABILITY_UNAVAILABLE|BUDGET_BLOCKED; CANCELLED -> CANCELLED_BY_USER|CANCELLED_BY_AMENDMENT; SUPERSEDED -> SUPERSEDED_BY_FALLBACK|SUPERSEDED_BY_REWORK; CREATED|RUNNING|VERIFYING|AUDITING|REWORK_REQUIRED -> NONE. Invalid pairs prohibited. AuditResult values are never run/attempt statuses; SUPERSEDED is a run status, never an audit result. cite: kit/PRODUCT_SPEC.md:1191-1215.

### §14B EXECUTION_ATTEMPT

ExecutionAttempt (immutable subordinate of one run): attempt_id, project_id, task_id, run_id, routing_assignment_id|null, attempt_no (monotonic per routing_assignment_id; UNIQUE(routing_assignment_id, attempt_no) when non-null), run_attempt_sequence (monotonic per run; UNIQUE(run_id, run_attempt_sequence)), attempt_type: AttemptType, provider, provider_instance, model, canonical_provider_id, canonical_model_id, output_artifact_refs[], material_contribution: bool, started_at|null, ended_at|null, status: ExecutionAttemptStatus, error_ref, usage_ref, input_ref, output_ref, retry_reason, fallback_reason. cite: kit/PRODUCT_SPEC.md:1223-1248.
 ENUM AttemptType: INITIAL | RETRY | FORMAT_RETRY | PROVIDER_RETRY | VERIFICATION_RETRY | TOOL_RETRY. cite: kit/PRODUCT_SPEC.md:1250-1257.
 Rules: retry = new attempt, history immutable; run keeps strategy/route unless FallbackPolicy changes it; every materially contributing invocation traceable to exactly one attempt; usage/time/error attach at attempt level when available; run status derived from attempts + verification + audit. cite: kit/PRODUCT_SPEC.md:1259-1284.
 Linear lifecycle (auditor-sanctioned OBS-1 line; no new edge invented): CREATED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED (terminal set for the attempt); a finished attempt never reopens.
 Correction: verification/audit correction = new run. Fallback: same logical route/strategy = same run + new attempt with fallback_reason; material route/strategy change = new run; decision deterministic from FallbackPolicy. cite: kit/PRODUCT_SPEC.md:1276-1285.
 Client rule: provider clients use max_retries 0 (no hidden recovery); runner retries only from RoutingDecision-bound RunConfig; each result posted as SdkRunResult carrying output_ref. cite: kit/PRODUCT_SPEC.md:1648-1652.

### §15 AMENDMENTS

Classes: CONTRACT_AFFECTING (touches any contract_hash-covered field: goal, requirements, acceptance criteria, permissions, routing/retry/fallback/optimization/verification/audit policy refs, workspace constraints, required outputs) vs NON_CONTRACT_AFFECTING (runtime metadata only, proven outside hash). cite: kit/PRODUCT_SPEC.md:1291-1301.
 effective_from: IMMEDIATE | NEXT_RETRY | NEXT_TASK | NEXT_PHASE | FUTURE_ONLY. scope: GLOBAL | PHASE | TASK. cite: kit/PRODUCT_SPEC.md:1420-1430.
 NEXT_RETRY rule: non-contract-affecting may apply to next attempt in-run; contract-affecting MUST NOT reuse the run: convert to AMENDMENT_RESTART at retry boundary, terminalize current non-terminal run per amendment rules, new contract version/hash, new TaskPackage, new run bound to new hash, next execution is Attempt-001 of the new run. One run = exactly one contract_hash for life. cite: kit/PRODUCT_SPEC.md:1303-1318.
 Terminal-task rule: IMMEDIATE never reopens COMPLETED/FAILED/CANCELLED; no new run attaches; Director rejects or creates a NEW task (new task_id, linked via supersedes_task_id/parent_task_id) with its own lifecycle and historical refs. cite: kit/PRODUCT_SPEC.md:1320-1340.
 ENUM AmendmentStatus: PENDING | APPLIED | SUPERSEDED | REJECTED | CANCELLED. cite: kit/PRODUCT_SPEC.md:1342-1347.
 Amendment: amendment_id, project_id, amendment_sequence (monotonic per project_id; UNIQUE(project_id, amendment_sequence)), scope, effective_from, target, change, reason, created_at, source, status: AmendmentStatus. cite: kit/PRODUCT_SPEC.md:1349-1361.
 ContractActivationRecord (immutable, authoritative, persistent): activation_id, project_id, task_id, activation_sequence (monotonic per task_id; UNIQUE(task_id, activation_sequence)), contract_version, contract_sequence, contract_hash, previous_contract_hash|null, amendment_id|null, effective_from, activation_reason, activated_at, evidence_refs[]. One activation transaction: validate amendment -> deterministic precedence (GLOBAL then PHASE then TASK, ascending amendment_sequence; narrower scope wins ties) -> immutable contract version/hash -> allocate contract_sequence -> persist activation -> mark amendment APPLIED -> invalidate/repackage/re-plan. Recovery resolves the active contract ONLY from committed activations. cite: kit/PRODUCT_SPEC.md:1363-1418.
 IMMEDIATE rule: never rewrites historical run data; active non-terminal run to CANCELLED + CANCELLED_BY_AMENDMENT via recorded transition; terminal runs immutable; then (lifecycle permitting) new contract + hash + run bound to it. Terminal run never to SUPERSEDED via amendment (SUPERSEDED only via legal non-terminal transitions). cite: kit/PRODUCT_SPEC.md:1432-1456.
 AMENDMENT_REPACKAGE_RULE: new active contract INVALIDATEs not-yet-executed TaskPackages/AgentTasks (default: TaskPlan/PlannedSubtasks too); re-plan under new hash; reuse only with deterministic PlanCompatibilityRecord COMPATIBLE; new TaskPackage before Manager execution; stale execution prohibited (executing stale handoff raises CONTEXT_WRONG_CONTRACT_VERSION). cite: kit/PRODUCT_SPEC.md:1460-1476.

### §16 RETRY_POLICY

ReworkCounterRecord (authoritative, persistent, atomic updates, restart-safe): counter_id, project_id, scope_type, scope_id, counter_type: ReworkCounterType, value, limit, updated_at, version. ENUM ReworkCounterType: PHASE0_REWORK | RUNTIME_REWORK | VERIFICATION_REWORK | AUDIT_REWORK. Immutable run/audit/verification history stays the forensic source. cite: kit/PRODUCT_SPEC.md:1479-1505.
 RetryPolicy (immutable versioned): policy_id, version, executor_attempt_max, provider_retry_max, format_retry_max, verification_retry_max, verification_correction_max, audit_correction_max, runtime_correction_max, backoff_policy, created_at, hash. Contract.retry_policy_ref binds exact version. cite: kit/PRODUCT_SPEC.md:1507-1524.
 FallbackCounterRecord (authoritative, persistent, atomic; scope RUN per-run / TASK per-task): counter_id, project_id, task_id, run_id|null, scope_type, scope_id, value, limit, updated_at, version. ENUM FallbackCounterScope: RUN | TASK. Allowed only while all applicable counters below limit. cite: kit/PRODUCT_SPEC.md:1526-1553.
 FallbackPolicy (immutable versioned): policy_id, version, allowed_reasons[], fallback_chain[], same_run_rules, new_run_rules, max_fallbacks_per_run, max_fallbacks_per_task, created_at, hash. Contract.fallback_policy_ref + FallbackRecord.policy_ref bind exact version. cite: kit/PRODUCT_SPEC.md:1555-1569.
 Attempt budget: attempt_no monotonic per routing_assignment_id; run_attempt_sequence monotonic per run (UNIQUE both); initial_assignment_attempts = count of execution-producing assignments (one initial attempt each, counted in attempt_count, not in retry budget); executor_attempt_max = max ADDITIONAL attempts; global_attempt_cap = initial + executor max; per-type caps (provider/format/verification) are subsets; retry allowed only if per-type AND global budget remain; correction loop = new run, counters reset for it; Phase-0 counters separate. cite: kit/PRODUCT_SPEC.md:1571-1621.
 DEFAULTS: executor_attempt_max=3, provider_retry_max=2, format_retry_max=1, verification_retry_max=1, audit_correction_max=2, verification_correction_max=2, runtime_correction_max=3. cite: kit/PRODUCT_SPEC.md:1623-1631.
 Exhaustion: never automatic ESCALATE; disposition follows failure precedence / FallbackPolicy / failure-class policy; ESCALATE only when the canonical disposition selects it. cite: kit/PRODUCT_SPEC.md:1633-1638.
 Retry record fields: reason, attempt, failed_AC[], evidence_ref, owner. cite: kit/PRODUCT_SPEC.md:1642-1647.

### §17 FALLBACK_POLICY

Fallback reasons (frozen set): provider_fail | model_fail | timeout | rate_limit | context_overflow | invalid_output | verification_fail | capability_mismatch | context_missing | context_stale | context_conflict | context_truncated | context_wrong_contract | context_recovery_failed | context_summary_drift | provider_capability_mismatch | resource_unavailable | health_failure. cite: kit/PRODUCT_SPEC.md:1654-1676.
 FallbackRecord: fallback_id, project_id, task_id, source_run_id, replacement_run_id|null, source_attempt_id|null, reason, from_provider, from_model, to_provider, to_model, policy_ref, evidence_ref. Same-run fallback: replacement_run_id = source_run_id; material fallback: replacement_run_id = new run_id. No blind retry where fallback fits. cite: kit/PRODUCT_SPEC.md:1685-1703.

### §17A RETRY_FALLBACK_REWORK_SEMANTICS

Retry: same run strategy/route + NEW attempt. Fallback: may change provider/model/route/strategy (same logical route/strategy = same run + new attempt; material change = new run). Correction loop (after failed verification/audit): always NEW run. Old records immutable. cite: kit/PRODUCT_SPEC.md:1706-1735.
 Counters kept distinct: retry_count, fallback_count, correction_count, attempt_count. cite: kit/PRODUCT_SPEC.md:1737-1742.

### §17B CANONICAL_AUDIT_RESULT

ENUM AuditResult: PASS | REWORK | BLOCKED | ESCALATE | FAIL (canonical verdicts; immutable evidence). ENUM AuditHandlingDisposition: COMPLETE | REWORK | BLOCK | ESCALATE | FAIL (separate runtime decision; never rewrites the result). cite: kit/PRODUCT_SPEC.md:1751-1777.
 Semantics: PASS = all required criteria passed + evidence valid + context_integrity PASS + no blocking security/governance issue; REWORK = correctable defect, bounded correction policy applies; BLOCKED = missing evidence/input/dependency; ESCALATE = authority/policy/budget decision required or unresolved governance conflict; FAIL = terminal under current scope/contract. cite: kit/PRODUCT_SPEC.md:1779-1802.
 Rules: AuditRecord.result uses AuditResult; DevelopmentGate audit status uses AuditResult; all audit-bearing gates use the canonical enum, no local subsets; user override never rewrites; Director never converts to PASS without new independent evidence/audit. Exhausted budget preserves REWORK and escalates HANDLING to ESCALATE with reason REWORK_BUDGET_EXHAUSTED. cite: kit/PRODUCT_SPEC.md:1804-1816.

### §17C VERIFICATION_FAILURE_PRECEDENCE

AttemptExecutionGate: EVERY execution-producing attempt passes it immediately before provider/model/tool execution (initial, FORMAT_RETRY, provider retry, same-run fallback, any execution-producing retry; VERIFICATION_ONLY stays VERIFYING unless the verifier itself executes billable/external work). Checks (frozen order): provider health, model health, required capability compatibility, security/risk policy, current TaskContract + policy refs, resource ownership/capacity, budget coverage, cancellation/suspension state, authorization state for external side effects, current routing/fallback eligibility. cite: kit/PRODUCT_SPEC.md:1820-1860.
 Resource rule: revalidate a valid owned lease, else reserve/re-reserve before execution. Budget rule: billable attempt needs active BudgetReservation coverage; top-up/reserve atomically; hard denial blocks. Gate failure on CREATED uses PRE_RUN_FAILURE_DISPOSITION; on RUNNING-or-later uses ATTEMPT_GATE_FAILURE_DISPOSITION; no side effect after failure. cite: kit/PRODUCT_SPEC.md:1838-1860.
 Gate failure dispositions (frozen per class): BUDGET_BLOCKED (no new attempt; RUNNING with no compliant recovery -> FAILED/BUDGET_BLOCKED; recoverable top-up -> Task BLOCKED; compliant non-billable fallback first); RESOURCE_FAILURE (no call; same-run re-reserve only if policy + route unchanged; else fallback first; recoverable -> BLOCKED; else FAILED/RESOURCE_FAILURE + ESCALATED); POLICY_BLOCK (no call, no auto-execution; recoverable auth/dependency -> BLOCKED; authority conflict -> ESCALATED; terminally unsatisfiable -> FAILED/POLICY_BLOCK); CAPABILITY_UNAVAILABLE (fallback first; same-run only if route contract valid; material = replacement run; none -> FAILED/CAPABILITY_UNAVAILABLE + ESCALATED); HEALTH_FAILURE (provider/model health fallback per policy; none -> FAILED + BLOCKED/ESCALATED per recoverability). Fallback choice precedes terminalization; transitions recorded before replacement execution. cite: kit/PRODUCT_SPEC.md:1862-1913.
 Retry classes: VERIFICATION_ONLY_RETRY (verifier/check only; Task+Run stay VERIFYING; no new attempt unless verifier tracks one) vs EXECUTION_PRODUCING_RETRY (Task VERIFYING -> REWORK_PENDING reason EXECUTION_RETRY; run VERIFYING -> RUNNING for policy-allowed same-run retry/fallback; new attempt; Task back to EXECUTING; on completion Task EXECUTING -> VERIFYING, run RUNNING -> VERIFYING; never increments correction_count; material route/strategy change uses FALLBACK_REROUTE + new run). cite: kit/PRODUCT_SPEC.md:1914-1952.
 Runtime correction budget: verification_correction_count[task_id], audit_correction_count[scope_id], runtime_correction_count[task_id] (authoritative, persistent, restart-safe); verification loop needs verification AND runtime budget; audit loop needs audit AND runtime budget; every correction run increments runtime count; exhaustion -> ESCALATE. cite: kit/PRODUCT_SPEC.md:1954-1982.
 ENUM VerificationFailureClass: VERIFICATION_INFRA_FAILURE | OUTPUT_FORMAT_FAILURE | PROVIDER_OR_MODEL_CAPABILITY_FAILURE | IMPLEMENTATION_AC_DEFECT | SECURITY_OR_POLICY_FAILURE | UNKNOWN_FAILURE. ENUM FailureSeverity: LOW | MEDIUM | HIGH | CRITICAL. cite: kit/PRODUCT_SPEC.md:1988-2001.
 DETERMINISTIC_DISPOSITION (one event -> exactly one path): INFRA -> VERIFICATION_RETRY if budget else ESCALATE; FORMAT -> FORMAT_RETRY / FALLBACK / correction loop (LOW/MEDIUM/HIGH) / ESCALATE (CRITICAL); CAPABILITY -> FALLBACK / adaptation correction / ESCALATE; AC_DEFECT -> correction loop; SECURITY/POLICY -> BLOCKED (recoverable) / ESCALATE (conflict/authority) / FAIL (confirmed terminal violation); UNKNOWN -> BLOCKED + classification required. Severity never selects BLOCKED/ESCALATE alone. Correction loop = new run; fallback per FallbackPolicy. cite: kit/PRODUCT_SPEC.md:2003-2041.

### §18B COMPLETION_DISPOSITION

OverridePolicy (immutable, versioned, authoritative, persistent; user-only author/activate/supersede incl. NON_OVERRIDABLE lists): policy_id, version, created_at, hash, supersedes_policy_ref|null, accepted_risk_allowed: bool, allowed_source_states[], non_overridable_failure_classes[], non_overridable_ac_types[], non_overridable_gate_ids[], required_authority, post_override_rules[], evidence_requirements[]. Contract MUST reference exact override_policy_ref; AuditPolicy too where override behavior is relevant; NON_OVERRIDABLE derives only from the active policy. cite: kit/PRODUCT_SPEC.md:2315-2340.
 OverrideRecord (authoritative, persistent; never rewrites history): override_id, project_id, task_id, run_id|null, created_at, authorized_by, authorization_ref, original_result|null (null only when no AuditResult exists), override_source_state, override_reason, override_action, accepted_risks[], evidence_refs[], scope, status: OverrideRecordStatus. ENUM OverrideRecordStatus: ACTIVE | SUPERSEDED | CANCELLED. cite: kit/PRODUCT_SPEC.md:2342-2366.
 ENUM CompletionDisposition: VERIFIED_PASS | ACCEPTED_RISK | FAILED | CANCELLED. cite: kit/PRODUCT_SPEC.md:2374-2378.
 Accepted-risk completion: allowed ONLY from non-terminal Task via canonical override edge; preserves original AuditResult; terminalizes any active non-terminal run as CANCELLED_BY_USER (pre-audit case: RUNNING/VERIFYING/AUDITING/REWORK_REQUIRED runs to CANCELLED/CANCELLED_BY_USER; none existing = run_id null); terminal runs untouched; NEVER fabricates SUCCEEDED; FAILED tasks never convert (new superseding Task). Pre-audit accepted risk needs override_source_state + reason + accepted_risks[] + authorization_ref. cite: kit/PRODUCT_SPEC.md:2380-2447.

### §19A EXTERNAL_ACTION_IDEMPOTENCY

ENUM ActionExecutionStatus: CREATED | IN_PROGRESS | SUCCEEDED | FAILED | CANCELLED | UNKNOWN_EXTERNAL_STATE. cite: kit/PRODUCT_SPEC.md:2490-2496.
 ActionExecution (K13 schema; execution writer K06 per handoff): action_id, project_id, task_id, run_id, idempotency_key, authorization_ref, attempt, status: ActionExecutionStatus, external_ref, created_at, completed_at. cite: kit/PRODUCT_SPEC.md:2498-2510.
 Rules: no blind duplicate of messages, POST mutations, issue/PR actions, remote writes, charges; provider idempotency keys where supported, else persist + verify prior external state before repeat; unprotected-mutation retry without idempotency/replay protection prohibited. cite: kit/PRODUCT_SPEC.md:2512-2528.
 AuthorizationRecord (K13 schema; R2 writer Director, R3 writer user): authorization_id, project_id, task_id, run_id, risk_level, action, scope, granted_by, granted_at, expires_at, evidence_ref. Permission ladder: R0 auto when task-authorized; R1 task-contract authorization; R2 Director explicit record; R3 user explicit record; generated commands never gain privilege. cite: spec 19 range 2449-2481, 0C sec 8.

### §20A SECRET_CREDENTIAL_MODEL

SecretRef: secret_id, provider_id, type, scope, source, created_at, last_rotated_at. cite: kit/PRODUCT_SPEC.md:2564-2572.
 Rules: contracts/Managers/agents get SecretRefs, never raw secrets (unless technically unavoidable); raw secrets never in logs, telemetry, reports, prompts, governance artifacts, ArtifactRefs; redaction mandatory; access follows the permission model; OS secret store, no enterprise vault required. cite: kit/PRODUCT_SPEC.md:2574-2584.

### §21 GOVERNANCE_INTEGRITY

File location is not trust; trust needs verified integrity + provenance. cite: kit/PRODUCT_SPEC.md:2633-2650.
 GovernanceArtifact: artifact_id, version, phase0_work_id|null, hash, hash_algorithm, created_at, approved_by, source. cite: kit/PRODUCT_SPEC.md:2637-2646.
 K13 interfaces: hash-pinned record refs everywhere; watcher integrity check consumes GovernanceArtifact hashes (K08 reads).

### §21A TASK_PACKAGE_AND_AGENT_TASK

ENUM TaskPackageStatus: ACTIVE | CONSUMED | INVALIDATED. ENUM AgentTaskStatus: ACTIVE | CONSUMED | INVALIDATED. cite: kit/PRODUCT_SPEC.md:2654-2662.
 TaskPackage (bounded Director->Manager context): package_id, project_id, task_id, contract_hash, goal, context_refs[], input_refs[], requirements_ref, acceptance_criteria_refs[], workspace, permissions_ref, tools_ref, routing_policy_ref, retry_policy_ref, fallback_policy_ref, optimization_policy_ref, verification_policy_ref, audit_policy_ref, override_policy_ref, created_at, status: TaskPackageStatus, invalidated_at|null, invalidation_reason|null, superseded_by_ref|null, hash. cite: kit/PRODUCT_SPEC.md:2666-2692.
 AgentTask (bounded Manager->Agent context): agent_task_id, project_id, task_id, subtask_id|null, run_id, agent_id, contract_hash, goal, context_refs[], input_refs[], acceptance_criteria_refs[], workspace, permissions_ref, tools_ref, expected_outputs[], created_at, status: AgentTaskStatus, invalidated_at|null, invalidation_reason|null, superseded_by_ref|null, hash. cite: kit/PRODUCT_SPEC.md:2694-2718.
 Gates (frozen): large context via ArtifactRefs; contract_hash MUST equal active contract; ALL seven package policy refs MUST equal the active TaskContract refs (mismatch = CONTEXT_WRONG_CONTRACT_VERSION or POLICY_CONFLICT, missing = CONTEXT_MISSING, no execution); INVALIDATED handoffs rejected at Manager/Agent gates; handoff never relies on model memory. cite: kit/PRODUCT_SPEC.md:2720-2737.

### §21B DECISION_RECORD

DecisionRecord (supports pre-run + Phase-0 scope: nullable task/run): decision_id, project_id, task_id|null, run_id|null, phase_id|null, gate_id|null, scope, type, statement, reason, authority, created_at, evidence_refs[], supersedes_decision_id, status. Concurrent configuration edits resolve by version ordering, never silent rewrite. cite: kit/PRODUCT_SPEC.md:2747-2764.

### §21C VERIFICATION_RECORD

Scope ids (deterministic, canonicalized: normalized ids/refs, sorted arrays, deduped, same set = same id): RUN_OUTPUT "TASK:"+task_id+":RUN:"+run_id+":CONTRACT:"+contract_hash+":RUN_OUTPUT"; ATTEMPT_OUTPUT per attempt_id; MULTI_ATTEMPT_OUTPUT sha256(canonical_sorted(attempt_ids[])); ARTIFACT_SET sha256(canonical_sorted(artifact_refs[])); SUBTASK_OUTPUT per subtask_id. cite: kit/PRODUCT_SPEC.md:2768-2795.
 ENUM VerificationTargetType: RUN_OUTPUT | ATTEMPT_OUTPUT | MULTI_ATTEMPT_OUTPUT | ARTIFACT_SET | SUBTASK_OUTPUT. ENUM VerificationResult: PASS | RETRY | FALLBACK | REWORK | BLOCKED | ESCALATE | FAIL. ENUM VerificationHandlingDisposition: ACCEPT | RETRY_VERIFIER | RETRY_EXECUTION | FALLBACK | REWORK | BLOCK | ESCALATE | FAIL. ENUM CriterionVerificationResult: PASS | FAIL | BLOCKED | NOT_APPLICABLE. cite: kit/PRODUCT_SPEC.md:2797-2827.
 CriterionResult: criterion_result_id, ac_id, result: CriterionVerificationResult, severity, verification_method, evidence_refs[], failure_class|null, notes|null. cite: kit/PRODUCT_SPEC.md:2829-2838.
 VerificationRecord (immutable, authoritative, persistent): verification_id, verification_sequence (monotonic per scope, atomic, UNIQUE(scope, sequence)), supersedes_verification_id|null, project_id, task_id, subtask_id|null, run_id, verification_scope_id, verification_target_type, attempt_id|null, attempt_ids[], artifact_refs[], contract_hash, criterion_results[] (full objects or immutable refs), result: VerificationResult, handling_disposition, failure_class|null, created_at, started_at|null, ended_at|null, evidence_refs[]. Latest = highest sequence per scope. cite: kit/PRODUCT_SPEC.md:2840-2871.
 Canonical disposition: PASS -> ACCEPT, run VERIFYING->AUDITING, Task VERIFYING->AUDITING; RETRY -> RETRY_VERIFIER (stay VERIFYING) or RETRY_EXECUTION (explicit return-to-execution lifecycle); FALLBACK -> FallbackPolicy, same-run or replacement run; REWORK with budget -> Task REWORK_PENDING + run REWORK_REQUIRED + replacement run + counters increment; REWORK exhausted -> result preserved, handling ESCALATE, Task ESCALATED, run holds VERIFYING/SUSPENDED_BY_TASK, no replacement; BLOCKED -> Task BLOCKED, run holds SUSPENDED_BY_TASK; ESCALATE -> Task ESCALATED, run holds; FAIL -> Task FAILED + run FAILED/VERIFICATION_FAILED. Result immutable; missing evidence ref fails the criterion, never silent PASS. cite: kit/PRODUCT_SPEC.md:2873-2927.

### §21D FINALIZER

Finalizer (K13, src/agent_si/finalization/): assembles outcome ONLY from authoritative records; checks state/audit consistency; binds exact audit_ref (audit_ref.result MUST equal FinalizationRecord.audit_result); attaches output ArtifactRefs; finalizes accounting; settles/releases budget + resource reservations; writes FinalizationRecord; never rewrites history. cite: kit/PRODUCT_SPEC.md:2930-2945.
 FinalizationRecord: finalization_id, project_id, task_id, run_id|null, task_state, audit_ref|null, audit_result|null, completion_disposition: CompletionDisposition, override_ref|null, verification_ref|null, output_refs[], metric_refs[], completed_at, limitations[]. cite: kit/PRODUCT_SPEC.md:2947-2962.
 FINALIZATION_MAPPING: COMPLETED+PASS -> VERIFIED_PASS; COMPLETED+override -> ACCEPTED_RISK; FAILED -> FAILED; CANCELLED -> CANCELLED. Pre-run finalization (CANCELLED/FAILED before any run): run_id null, audit/verification refs null unless occurred, disposition CANCELLED/FAILED; never invent NOT_RUN. cite: kit/PRODUCT_SPEC.md:2964-2987.

### §21E TASK_PLAN_AND_PLANNED_SUBTASK

PlanCompatibilityRecord: plan_compatibility_id, project_id, task_id, old_contract_hash, new_contract_hash, task_plan_id, result: PlanCompatibilityResult, checked_fields[], evidence_refs[], created_at. ENUM PlanCompatibilityResult: COMPATIBLE | INCOMPATIBLE. Default: contract-affecting amendment = INCOMPATIBLE unless deterministic proof. cite: kit/PRODUCT_SPEC.md:2993-3014.
 ENUM TaskPlanStatus: CREATED | ACTIVE | INVALIDATED | COMPLETED | FAILED. ENUM PlannedSubtaskStatus: PLANNED | READY | RUNNING | BLOCKED | COMPLETED | FAILED | CANCELLED | INVALIDATED. cite: kit/PRODUCT_SPEC.md:3016-3031.
 TaskPlan (authoritative, persistent): task_plan_id, project_id, task_id, contract_hash, created_at, created_by, status: TaskPlanStatus, subtask_ids[], dependency_edges[], evidence_refs[], version, hash. cite: kit/PRODUCT_SPEC.md:3033-3046.
 PlannedSubtask: subtask_id, task_plan_id, project_id, task_id, parent_subtask_id|null, goal, task_class, risk: RiskLevel, required_capabilities[], knowledge_needs[], tool_needs[], acceptance_criteria_refs[], dependency_ids[], status: PlannedSubtaskStatus. cite: kit/PRODUCT_SPEC.md:3048-3063.
 Rules: AgentTask references subtask_id for planned subtasks; TelemetryEvent.subtask_id references PlannedSubtask; plan graph recoverable after restart. cite: kit/PRODUCT_SPEC.md:3065-3070.

### §25A RISK_LEVEL

ENUM RiskLevel (ordered): LOW < MEDIUM < HIGH < CRITICAL. Task/routing/optimization risk fields MUST use it; FailureSeverity never substitutes. Optimization constraint: risk <= max_risk. cite: kit/PRODUCT_SPEC.md:3151-3164.
 PolicyIdentity: TaskContract refs are the single sources of truth (audit->AuditPolicy; verification->VerificationPolicy+FailureDispositionPolicy; retry->retry_policy_ref; fallback->fallback_policy_ref; override->override_policy_ref; routing->routing_policy_ref; optimization->optimization_policy_ref). Nested refs in Verification/Audit/FailureDisposition policies MUST equal the active contract refs unless the contract delegates that field; conflict = POLICY_CONFLICT, execution blocked. cite: kit/PRODUCT_SPEC.md:3199-3235.
 PolicyLifecycleRecord (authoritative, persistent; status derived, never stored on the policy): policy_lifecycle_id, policy_ref, policy_id, policy_version, lifecycle_sequence (monotonic per policy_id), event: PolicyLifecycleEvent, created_at, reason, supersedes_policy_ref|null. ENUM PolicyLifecycleEvent: ACTIVATED | SUPERSEDED | RETIRED. Common immutable-policy fields: policy_id, version, created_at, hash, supersedes_policy_ref|null. Derived status: ACTIVE | SUPERSEDED | RETIRED. Required immutable policy objects: RoutingPolicy, OptimizationPolicy, RetryPolicy, FallbackPolicy, VerificationPolicy, AuditPolicy (+ OverridePolicy, FailureDispositionPolicy per §26A/§18B). cite: kit/PRODUCT_SPEC.md:3168-3269.

### §26A VERIFICATION_AND_AUDIT_POLICY

ENUM VerificationRequirement: STANDARD | ENHANCED. ENHANCED = all required deterministic checks + independent semantic/security verification + required evidence per criterion + no silent verifier bypass + capability-sensitive checks on explicit pin/unverified capability; retry/correction handling still follows RetryPolicy + FailureDispositionPolicy; never changes audit level by itself. cite: kit/PRODUCT_SPEC.md:3357-3374.
 VerificationPolicy (immutable, versioned): policy_id, version, created_at, hash, requirement: VerificationRequirement, required_types[], retry_policy_ref, evidence_requirements[], failure_disposition_policy_ref. cite: kit/PRODUCT_SPEC.md:3397-3407.
 FailureDispositionPolicy (immutable, versioned, authoritative, persistent): policy_id, version, created_at, hash, supersedes_policy_ref|null, failure_class_rules[], severity_rules[], retry_policy_ref, fallback_policy_ref, override_policy_ref. VerificationPolicy.failure_disposition_policy_ref binds it exactly; no dangling generic refs. cite: kit/PRODUCT_SPEC.md:3378-3395.
 AuditPolicy (immutable, versioned): policy_id, version, created_at, hash, audit_requirement, minimum_independence_level, required_context_integrity, retry_policy_ref, override_policy_ref, manual_review_rules[]. ENUM AuditRequirement: REQUIRED_L2 | REQUIRED_L3 | REQUIRED_L4_MANUAL (NONE prohibited; no silent no-audit success path). Invariant: level(REQUIRED_L2)=L2, level(REQUIRED_L3)=L3, level(REQUIRED_L4_MANUAL)=L4; minimum_independence_level >= level(requirement); L4_MANUAL needs L4 + manual_reviewer_ref. cite: kit/PRODUCT_SPEC.md:3409-3451.

### §27A BUDGET_GATE

Atomicity: hard-budget admission uses compare-and-reserve: spent + reserved + requested_reservation <= hard_limit, else block (unless explicitly authorized override). Settlement dedupe_key deterministic: reservation_id + provider_usage_evidence_ref, or reservation_id + provider_request_ref + PENDING_RECONCILIATION when evidence missing; settlement_id NEVER part of dedupe identity. UNIQUE(reservation_id, provider_usage_evidence_ref) where present; recovery may recreate settlement ops without double-settling. Missing evidence after possible billable execution -> status PENDING_RECONCILIATION, reservation held conservatively. Restart: load ACTIVE/CREATED reservations, reconcile with provider usage/cost evidence, settle idempotently, release expired unused, never double-settle. cite: kit/PRODUCT_SPEC.md:3488-3539.
 BudgetState: project_id, currency, budget_limit, soft_limit, hard_limit, spent, reserved, remaining_derived (= hard_limit - spent - reserved, CALCULATED, never independent truth; recomputed transactionally), updated_at. cite: kit/PRODUCT_SPEC.md:3543-3604.
 ENUM BudgetReservationStatus: CREATED | ACTIVE | SETTLED | RELEASED | EXPIRED | FAILED. BudgetReservation: reservation_id, project_id, task_id, run_id, estimated_amount, reserved_at, expires_at, status. cite: kit/PRODUCT_SPEC.md:3555-3572.
 ENUM BudgetSettlementStatus: PENDING_RECONCILIATION | SETTLED | FAILED | VOIDED. BudgetSettlement: settlement_id, reservation_id, provider_usage_evidence_ref|null, provider_request_ref, dedupe_key, actual_amount|null, difference|null, status, settled_at|null, source. Billable attempts need provider_request_ref for recovery. cite: kit/PRODUCT_SPEC.md:3574-3604.
 Flow (frozen): ModelRouter -> scheduler precheck -> BudgetGate -> execution; reservations before parallel cloud runs; soft limit warns, hard limit blocks unless user overrides; local zero-marginal-cost work may continue if policy allows. cite: kit/BUILD_PLAN.md:640-649, 0C sec 10.

### §28 ROUTING_DECISION

RoutingAssignment (authoritative, persistent; one or many per decision; SPLIT/PARALLEL/HYBRID use multiple when providers/models/roles/stages materially participate): assignment_id, project_id, task_id, run_id, subtask_id|null, role|null, stage|null, route, provider, provider_instance|null, model, capability_evidence_refs[], resource_state_ref, budget_reservation_ref|null, routing_policy_ref, optimization_policy_ref, status: RoutingAssignmentStatus. ENUM RoutingAssignmentStatus: PLANNED | BOUND | RUNNING | COMPLETED | FAILED | CANCELLED | SUPERSEDED. ExecutionAttempt references routing_assignment_id when applicable; replay = decision + assignments + snapshot. cite: kit/PRODUCT_SPEC.md:3632-3672.
 RoutingEvidenceSnapshot (authoritative, persistent; decision MUST reference it; live state never substitutes history): routing_snapshot_id, project_id, task_id, run_id, created_at, provider_health_snapshot, model_health_snapshot, resource_state_snapshot, budget_state_snapshot, candidate_snapshot[], policy_versions[], capability_evidence_refs[], hash. cite: kit/PRODUCT_SPEC.md:3674-3699.
 RoutingDecision (authoritative, persistent; K13 schema, K04 writer per 0C map): decision_id, project_id, task_id, run_id, routing_snapshot_id, routing_policy_ref, optimization_policy_ref, retry_policy_ref, fallback_policy_ref, verification_policy_ref, audit_policy_ref, override_policy_ref, candidate_models[], candidate_providers[], selected_provider|null, selected_model|null, routing_assignment_ids[], route, strategy, reason, eligibility_source, capability_state, required_verification, eligibility_branch_evidence_refs[], capability_evidence_refs[], provider_health_ref, model_health_ref, resource_state_ref, risk_override, estimated_cost, estimated_latency, optimization_score, fallback_chain[]. UI exposes WHY_THIS_MODEL from this record. SPLIT decisions carry local_draft + cloud_verify assignments atomically. cite: kit/PRODUCT_SPEC.md:3701-3741.
 RoutingPolicy (immutable, versioned; K13 schema, K04 writer): policy_id, version, created_at, hash, task_class, risk_level, strict_min, tolerant_min, confidence_min, sample_min, freshness_requirement, local_allowed: bool, split_allowed: bool, cloud_required: bool. Bootstrap thresholds (evidence-gated, branch A only, hard gates always apply): 100% measured -> LOCAL (safe classes); >=85% -> LOCAL with tolerant parser where permitted; 50-85% -> SPLIT (local draft + cloud verify); <50% or NO-DATA -> CLOUD; score alone never grants eligibility; NO-DATA never grants LOCAL. cite: kit/PRODUCT_SPEC.md:3278-3353.
 OptimizationPolicy (immutable, versioned; K13 schema, K04 writer): policy_id, version, created_at, hash, required_quality, max_risk, weight_quality, weight_cost, weight_latency, weight_cloud_tokens, local_preference, deadline, budget_limit. Primary: quality >= required AND risk <= max; then minimize expected cost, latency, cloud tokens, resource pressure. Quality/safety override savings. cite: kit/PRODUCT_SPEC.md:3455-3483.

### §37 CAPABILITY_ARCHITECTURE

Layering (frozen): Core -> CapabilityService -> CapabilityRepositoryInterface -> adapter (SQLite or future). Core NEVER imports SQLite or any adapter; capability base is optional evidence, never the only legal path. cite: kit/PRODUCT_SPEC.md:3901-3918.
 K13 interfaces: CapabilityRepositoryInterface (port owned by K13, implemented outside K13: read-only capability evidence rows; original external data never mutated without authorization; stale copies versioned, never current evidence). Optional configured inputs keep stable refs; NOT_CONFIGURED status when absent and execution continues. cite: kit/PRODUCT_SPEC.md:3911-3918.

### §38 RESOURCE_SCHEDULER

Phases (frozen order): precheck (read-only eligibility/capacity, may emit immutable ResourceStateSnapshot, never reserves) -> RoutingDecision -> reserve (creates lease/reservation; may fail on race/capacity; failures follow pre-run/fallback policy) -> AttemptExecutionGate. Historical decisions replay from the precheck snapshot; execution starts only after a successful reserve when required. cite: kit/PRODUCT_SPEC.md:3942-3948.
 ResourceScheduler config: max_parallel_global, max_parallel_per_provider, max_parallel_per_model, local_gpu_slots, local_cpu_slots, memory_budget, gpu_memory_budget, queue_policy, priority_policy. Reserve outputs: ResourceLease | ResourceReservation | queue_position | estimated_start | lease_timeout. Excess demand queues, never drops. No unlimited local parallel inference. cite: kit/PRODUCT_SPEC.md:3950-3958.
 ENUM ResourceLeaseStatus: CREATED | ACTIVE | RELEASED | EXPIRED | FAILED | ORPHANED. ENUM ResourceReservationStatus: CREATED | ACTIVE | FULFILLED | RELEASED | EXPIRED | FAILED | ORPHANED. cite: kit/PRODUCT_SPEC.md:3926-3928.
 ResourceLease (authoritative, persistent): lease_id, project_id, task_id, run_id, resource_type, resource_id, owner_run_id, acquired_at, expires_at, released_at|null, status: ResourceLeaseStatus, capacity_claim, evidence_ref. ResourceReservation: reservation_id, project_id, task_id, run_id, resource_type, resource_id|null, owner_run_id, requested_capacity, created_at, expires_at, fulfilled_at|null, released_at|null, status: ResourceReservationStatus, evidence_ref. ResourceStateSnapshot (authoritative + persistent when referenced by a routing snapshot): resource_state_snapshot_id, project_id, task_id, run_id, created_at, available_gpu_slots, available_cpu_slots, memory_available, gpu_memory_available, queue_depth, provider_capacity_refs[], hash. cite: kit/PRODUCT_SPEC.md:3930-3940.
 Recovery: reconcile persisted state with actual scheduler/provider state; expired leases never trusted; orphans released/expired deterministically; recovered runs revalidate ownership before execution. cite: kit/PRODUCT_SPEC.md:3934, 3954.
 Ownership note: K13 owns execution gating (src/agent_si/runtime/scheduler/); work scheduling (timers/launchers) lives in automation/ under K08 (0C sec 7/§12; distinct layers, no clash).

### §40 ARTIFACT_REF

ArtifactRef: artifact_id, path, version, hash, hash_algorithm, media_type, size, created_at, source, owner, read_scope, range, trust_level, provenance_ref. cite: kit/PRODUCT_SPEC.md:3973-3976.
 Rule: prefer ARTIFACT_REF over repeated INLINE_CONTENT (docs, reports, code, tests, audits, logs, schemas, large context); bulk inline transfer re-issued by ref at handoff audit. cite: kit/PRODUCT_SPEC.md:3977-3980.

### §41 AUTHORITATIVE_VS_DERIVED

Authoritative set (every member has a K13 schema in this manifest; persistence per §42): Projects, TaskContracts, ContractActivationRecords, TaskPackages, AgentTasks, TaskPlans, PlannedSubtasks, PlanCompatibilityRecords, ExecutionRuns, ExecutionAttempts, Transitions, Amendments, DecisionRecords, Phase0WorkRecords, VerificationRecords, AuditRecords, AuditExecutionRecords, IncidentRecords, ContextIntegrityRecords, SuspensionRecords, LateResultReconciliationRecords, MetricRecords, PricingSnapshots, TelemetryEvents, FallbackRecords, OverrideRecords, RoutingDecisions, RoutingAssignments, RoutingEvidenceSnapshots, ResourceStateSnapshots, ResourceLeases, ResourceReservations, RoutingPolicies, OptimizationPolicies, PolicyLifecycleRecords, VerificationPolicies, AuditPolicies, OverridePolicies, FailureDispositionPolicies, RetryPolicies, FallbackPolicies, FallbackCounterRecords, ReworkCounterRecords, AuthorizationRecords, ActionExecutions, BudgetStates, BudgetReservations, BudgetSettlements, CapabilityEvidence, ProviderContracts, ModelContracts, UsageReportingCapabilities, FinalizationRecords. cite: kit/PRODUCT_SPEC.md:3982-3987.
 Name note: the §42 minimum-domain token revision_counter_records denotes ReworkCounterRecord (§16); single canonical name used here.
 Derived set: PROJECT_STATE, dashboards, summaries, analytics, download reports, AI interpretations. Conflict: authoritative wins; PROJECT_STATE regeneratable. cite: kit/PRODUCT_SPEC.md:3986-3990.

### §42 APPLICATION_STORAGE

Every authoritative domain record persisted; any later-added authoritative entity gains persistence automatically. Minimum domains = the §41 set. cite: kit/PRODUCT_SPEC.md:3992-4012.
 Repository abstraction frozen: domain core never hard-codes SQLite; storage behind repository ports (§ports); immutable history where specified; stable ids; project/task/run links; timestamps; referential integrity; version+hash fields where contracts/governance require; retention; additive-only migrations with backup, validation, rollback; replay/audit-friendly retrieval. cite: kit/PRODUCT_SPEC.md:4004-4012.

### §42A SDK_TRACING_PRIVACY_POLICY

SDKTracingPolicy: enabled, destination, data_classification, redaction_required, allow_model_input, allow_model_output, allow_tool_arguments, allow_tool_results, allow_file_content, retention_policy, external_export_allowed, project_scope. cite: kit/PRODUCT_SPEC.md:4018-4020.
 Defaults (frozen): sensitive/local/private workloads -> external_export_allowed=false, redaction_required=true, allow_file_content=false. Explicit per-project + per-run policy; secrets never exported; local/private traces stay local without explicit authorization; app telemetry complete with tracing off; tracing is diagnostic instrumentation, never the authoritative store. cite: kit/PRODUCT_SPEC.md:4022-4028.
 0C DECISION (B0B-UNCOVERED_ARCH-404): default DISABLED (sdk_tracing_enabled=false for every project and run; enabling needs explicit project+run policy, still local-processor-only by default; hosted export additionally needs authorization + configured key + redaction; secrets-bearing runs refuse external export without explicit authorization). cite: 0C sec 9.

### §43 ORCHESTRATION_RUNTIME

Architecture (frozen): Domain/Core -> OrchestrationInterface -> OpenAIAgentsSDKAdapter. Default USE_SDK_UNLESS_DOCUMENTED_CRITICAL_BLOCKER; no SDK rebuild without documented reason; replacement needs evidence + decision record + independent audit. cite: kit/PRODUCT_SPEC.md:4032-4046.
 K13 interfaces: OrchestrationInterface.run_turn (single engine entry behind the backend chat-stream caller), OpenAIAgentsSDKAdapter (SDK calls only; Chat Completions for non-OpenAI providers, never assumed Responses API; client max_retries=0; runner retries only from RoutingDecision-bound RunConfig; results as SdkRunResult{output_ref}). cite: kit/PRODUCT_SPEC.md:4040-4053, 0C sec 2.

### §44 EXTENSION_REGISTRIES

Frozen extension points: ProviderRegistry, ModelRegistry, CapabilityRegistry, ToolRegistry, KnowledgeSourceRegistry, VerifierRegistry, AuditorRegistry. New extension never requires core rewrite; same-named registrations from different runtimes stay distinct; registries own lookup + health views only (never execution, routing, or secret values). cite: kit/PRODUCT_SPEC.md:4055-4061.

### §45 PROJECT_MEMORY

PROJECT_STATE is DERIVED; regenerate + validate from authoritative records before continuation; never trust model memory alone. cite: kit/PRODUCT_SPEC.md:4064-4078.
 Fast recovery order (frozen): active TaskContract -> active run or null -> latest transitions -> latest applicable amendments -> unresolved ContextIntegrityRecords -> unresolved IncidentRecords -> latest VerificationRecord -> latest AuditRecord -> active policy refs -> active TaskPackage/TaskPlan/AgentTask refs; then regenerate summaries. Full recovery additionally loads MASTER_PLAN artifact, Phase0WorkRecords, TaskPlans/PlannedSubtasks, attempts, routing decision + snapshot, budget/resource records, rework/fallback counters, authorization/override/finalization records, telemetry/metric records. cite: kit/PRODUCT_SPEC.md:4068-4076.

### §45A CONTEXT_INTEGRITY_AND_CONTEXT_VIOLATIONS

ContextViolation types (frozen): CONTEXT_MISSING | CONTEXT_STALE | CONTEXT_CONFLICT | CONTEXT_TRUNCATED | CONTEXT_UNAUTHORIZED_EXPANSION | CONTEXT_WRONG_TASK | CONTEXT_WRONG_CONTRACT_VERSION | CONTEXT_ARTIFACT_UNAVAILABLE | CONTEXT_RECOVERY_FAILED | CONTEXT_SUMMARY_DRIFT. cite: kit/PRODUCT_SPEC.md:4084-4086.
 ContextIntegrityRecord (authoritative, persistent, mandatory): context_event_id, incident_ref|null, project_id, task_id, run_id|null, actor, detected_by, type, severity (IncidentSeverity), expected_context_refs[], actual_context_refs[], missing_refs[], conflicting_refs[], contract_hash, detected_at, impact, resolution, resolved_at, evidence_refs[]. cite: kit/PRODUCT_SPEC.md:4086.
 Rules: incident rows index only (never duplicate truth; mirrored rows carry the incident id); violations survive compression/replacement/repackage/audit; summaries reference unresolved items; handoffs carry ArtifactRefs + contract_hash; recovery verifies contract/run/refs/amendments/audit/revision/context incidents; conflict with authoritative records creates CONTEXT_CONFLICT (records win); unrecoverable context -> BLOCKED/ESCALATED; HIGH/CRITICAL unresolved blocks PASS; auditor receives the register + resolution evidence + contract refs and records context_integrity; PASS forbidden unless context_integrity PASS for the scope. cite: kit/PRODUCT_SPEC.md:4088-4103.
 ContextRecoveryCheck (frozen predicate): expected_contract_hash == recovered_contract_hash AND required_refs_available AND unresolved_context_incidents_loaded AND latest_amendments_loaded AND active_run_consistent; failure -> CONTEXT_RECOVERY_FAILED -> BLOCKED/ESCALATED. cite: kit/PRODUCT_SPEC.md:4107-4111.

### §45B CANCELLATION_FINALIZATION

Cancellation is not rollback: never deletes telemetry; completed calls stay authoritative; partial usage/time/cost finalized where measurable; committed side effects + partial outputs kept under retention; active attempts to CANCELLED; run reason from RunTerminationReason only (user -> CANCELLED_BY_USER; amendment -> CANCELLED_BY_AMENDMENT; policy violation -> FAILED/POLICY_BLOCK; resource/system failure -> FAILED/RESOURCE_FAILURE; generic CANCELLED prohibited as a reason); budget settled/released; leases/reservations released; audit/verification history immutable. cite: kit/PRODUCT_SPEC.md:4113-4117.

### §46 INCIDENTS

ENUM IncidentSeverity: LOW | MEDIUM | HIGH | CRITICAL (shared by ContextIntegrityRecord.severity + IncidentRecord.severity). cite: kit/PRODUCT_SPEC.md:4124-4128.
 IncidentRecord: incident_id, project_id, timestamp, task_id, run_id, actor, detected_by, severity, type, description, root_cause, impact, action, regression_test, status. Types (frozen): workspace_violation | provider_failure | model_failure | scheduler_failure | test_failure | audit_failure | scope_deviation | security_issue | retry_exhausted | fallback_exhausted | unsafe_action | data_corruption_risk | capability_mismatch. Incidents index context violations only (truth stays in ContextIntegrityRecord). cite: kit/PRODUCT_SPEC.md:4130-4132.

### §47 REPORT_EXPORT

Reports generate from authoritative stored telemetry only; AI never replaces measured tables (optional DERIVED narratives allowed, labelled, never overriding). Flow: stored data -> deterministic aggregation -> report dataset -> optional AI summary -> export. Formats: JSON, CSV, printable HTML/PDF (XLSX optional later). cite: kit/PRODUCT_SPEC.md:4134-4143.
 K13 interface: ReportDatasetBuilder.build (src/agent_si/reports/) over records only.

### §49 PROJECT_OVERVIEW

Overview exposes (all derived from stored telemetry; no generated numbers): project age, active work time, AI execution time, cloud/local AI time, cloud tokens, tokens by provider/model, cloud/local calls, cost where valid, task counts (total/active/completed/failed/re-execution), audit counts (PASS/REWORK/BLOCKED/ESCALATE/FAIL), models/providers used, latest activity, current phase, completion disposition, accepted-risk state. cite: kit/PRODUCT_SPEC.md:4157-4163.
 K13 interfaces: dataset builder (§59) + MetricRecord aggregates (§10/§11).

### §51 PHASE0_REQUIRED_ARCH_ANALYSIS

K13-bound arch inputs (frozen checklist): SDK integration boundary; project model; telemetry subsystem (collection, time, cost, event storage, analytics, report export); task/run model + routing; local-AI discovery + optional capability base; scheduler; authorization records + governance integrity; tracing policy; BudgetGate with reservation + settlement; provider usage-reporting capability. cite: kit/PRODUCT_SPEC.md:4204-4209, kit/BUILD_PLAN.md:1230.
 Target layout anchors: composition root src/agent_si/backend/app.py create_app + sidecar handshake + router guard (kit/DEV_HANDBOOK.md:91-126, 0C sec 1; file owned by K02 per 0C map, interface frozen here).

### §53 MVP_CORE

Headless pipeline records (every hop persisted): Project -> Task -> Manager (TaskPackage) -> planner/router -> worker (AgentTask) -> verify -> audit -> result; automatic capture of task, run, state, time, provider, model, route, tokens where available, local/cloud usage, retries, fallback, verification, audit, errors. cite: kit/PRODUCT_SPEC.md:4216-4219.
 K13 interfaces: TaskPackage/AgentTask (§21A), TelemetryEvent envelope (§55), FinalizationRecord (§21D).

### §55 TELEMETRY_EVENT

TelemetryEvent (envelope, NOT a multi-metric record): event_id, project_id (REQUIRED), timestamp, task_id (null only for project/system/provider events), run_id (null before run creation or for non-run events), attempt_id (null when not attempt-scoped), subtask_id (null when not subtask-scoped), parent_id, role, task_class, risk, state, route, split_strategy, provider, model, provider_instance, event_type, retry, verification_ref, audit_ref, re-execution, error_ref, fallback_reason, capability_rule, capability_evidence_ref, routing_decision_ref, routing_snapshot_id, resource_state_ref, metric_refs[], final_status. Event type sets required identity fields. cite: kit/PRODUCT_SPEC.md:4247-4261.
 Rules: measurements travel as independent MetricRecord entries (input_tokens from provider usage API; cost from pricing snapshot; wall_time from monotonic clock); one shared metric state/source across heterogeneous measurements prohibited; MetricRecord owns value/state/source; unknown event_type rejected (new types = new vocabulary version, never silent); duplicate event_id returns the stored record; envelopes + MetricRecords append-only, corrections are new records. cite: kit/PRODUCT_SPEC.md:4247-4261.
 id shape: event_id stable string. version+hash: immutable, append-only.

### §59 FINAL_REPORT

Report dataset (frozen key set, metrics from records only): PROJECT, GOAL, SCOPE, ARCH, PHASES, TASKS, RUNS, MANAGERS, AGENTS, MODELS, PROVIDERS, ROUTES, SPLIT_STRATEGIES, ROUTING_DECISIONS, FALLBACKS, TIME, TOKENS, COST, LOCAL_CALLS, CLOUD_CALLS, RETRIES, REWORKS, FAILURES, INCIDENTS, DEVIATIONS, AMENDMENTS, SECURITY, TESTS, AUDITS, LIMITATIONS, RISKS, CONTEXT_INTEGRITY, CONTEXT_VIOLATIONS, BUDGET, SDK_TRACING_POLICY, USAGE_REPORTING_CAPABILITY, FINAL_STATUS. Director may add narrative over measured data. cite: kit/PRODUCT_SPEC.md:4276-4281.
 K13 interfaces: ReportDatasetBuilder rows per demo/fixture with referenced artifacts, versions, provider set, audit identities. cite: kit/PRODUCT_SPEC.md:4276-4281.

### §60 CORE_RULES (K13 R-list)

K13-owned: R01, R04-R05, R08-R11, R13, R21-R25, R27, R30-R32, R37-R39, R45-R47, R50, R52-R54, R56-R57, R59-R60, R62, R64-R82, R84-R88, R91-R98, R100-R106, R110-R112, R114, R116, R118-R121, R123-R128, R130-R131, R133-R134, R136, R139, R141-R144, R147-R148, R150, R152-R153, R155-R157, R161, R163, R165-R169, R171, R175, R179-R181, R184-R189, R191, R198. cite: kit/BUILD_PLAN.md:1239.
 Load-bearing pins (all other R-ids hold verbatim per kit/PRODUCT_SPEC.md:4283+): R66 run uses run_sequence + revision_no; R119 run created as nullable-selection skeleton before decision + budget; R150 contract/package exact immutable policy refs; R154 hard-budget compare-and-reserve + deterministic settlement dedupe; R164 verification/audit refs resolve to exact immutable canonical policy objects; R179 run has one canonical persistent schema + atomic per-task run_sequence; R180 task transitions use CAS + state_version + UNIQUE(task, transition_sequence); R181 active contract derives only from committed activations; R190 BudgetState.remaining derived, never truth; R191 MetricRecord provenance field is source. cite: kit/PRODUCT_SPEC.md:4283+.
 Non-K13 R-ids are out of scope for this manifest (owned by their packages).

## Ports + interfaces (frozen names; owner package per entry; 0C map: 0C sec 12)

Repository ports (K13; one per aggregate in src/agent_si/storage/, adapters in src/agent_si/adapters/sqlite/, core never imports adapters):
 ProjectRepository | TaskContractRepository | ContractActivationLog | TaskTransitionLog | ExecutionRunRepository | ExecutionAttemptLog | AmendmentRepository | PolicyRepository (per policy type) + PolicyLifecycleLog | RetryFallbackCounterStore (atomic incr) | VerificationLog | SuspensionLog | RoutingDecisionLog | RoutingEvidenceSnapshotLog | ResourceLeaseRegistry | ResourceReservationRegistry | BudgetLedger (reservations + settlements) | TelemetryEventLog | MetricRecordLog | GovernanceArtifactLog | DecisionLog | FinalizationLog | ContextIntegrityLog | IncidentIndex | ReportDatasetBuilder.
 Frozen operation shape per port: load(id) -> record|null; append(record) -> record (immutable logs; duplicate idempotent key returns stored record); compare_and_set(id, expected_version, record) -> record (mutable aggregates; loser re-reads); list_by(query) -> records (replay/audit-friendly order). Counters: increment(scope, kind, limit) -> value (atomic, restart-safe). CAS + UNIQUE rules per record section above.
 Execution interfaces: OrchestrationInterface.run_turn (K13) | OpenAIAgentsSDKAdapter (K13) | SdkRunResult{output_ref} (K13) | AttemptExecutionGate.check (K13) | Finalizer.finalize (K13) | ResourceScheduler.precheck/reserve (K13) | CapabilityRepositoryInterface.read (K13 port, implemented outside K13) | BudgetGate.compare_and_reserve/settle (K04 code, K13 schemas §27A) | ModelRouter.select (K04 code, K13 schemas §28) | GuardedToolDispatcher.dispatch (K06 code, bound by the K13 SDK adapter) | create_app(settings, auth_hook, rate_hook, model_factory) composition root (file owned by K02 per 0C map; startup order + guard contract frozen here per §51).
 Router guard contract (frozen): path -> action class (chat stream/cancel, export, authorizations, projects, settings, console reads) + auth/rate hooks; chat POSTs need actor header; single-user desktop: UI session token check first in every USER write handler; reads need no token. cite: 0C sec 1, kit/DEV_HANDBOOK.md:115-126.

## K03-to-K06 ASK-UI handoff (frozen)

Record schemas stay K13: permission ASK state uses AuthorizationRecord (§19A: authorization_id, scope, action, granted_by, granted_at, expires_at, evidence_ref) + ActionExecution (§19A: action_id, idempotency_key, status) for the approved leg; user answers arrive as buttons (allow once / for this project / deny) resuming the parked run. Execution writer stays K06: ASK-UI files live in src/agent_si/toolguard/ + frontend/src/ask/ (0C sec 12 map); ASK evaluation persists before use; user authorization creates the AuthorizationRecord consumed by the R2/R3 gate. cite: kit/BUILD_PLAN.md:539-540, kit/BUILD_PLAN.md:807-809, 0C sec 12.
 Same pattern elsewhere in this manifest: routing/budget schemas K13 with writers in K04 (§28, §27A); audit/verification schemas K13 with assurance writers in K03 (§21C, §17B).

## 0C reconciliation (naming authority 0C; 0C wins; COMPLETE, 0C present)

| term | 0C sec | manifest § | winner |
| revision_no (run correction counter) | 0C sec 4 glossary + §13 R66 pin | §14 | 0C (spec §14 body token correction_no denotes the same counter) |
| create_app composition root location + signature | 0C sec 1 | §51 + ports | 0C (file owned by K02; interface frozen here) |
| module prefixes incl. iface/frozen_manifest/ | 0C sec 12 map | ports | 0C (clash list EMPTY; scheduler layers distinct) |
| default Manager provider/model meta + model id | 0C sec 3, 0C sec 4 | §3B, §0 | agree (shipped preset, user-changeable) |
| tracing default DISABLED | 0C sec 9 decision | §42A | 0C (decides B0B-UNCOVERED_ARCH-404) |
| K13 runtime/scheduler vs K08 automation scheduler | 0C sec 7, 0C sec 12 | §38 | 0C (execution gating vs work scheduling) |
| TaskPackage/AgentTask bounded context + policy-ref gate | 0C sec 4 | §21A | agree |
| RoleModelProfile modes PINNED\|pool\|AUTO | 0C sec 3 | §8 | 0C (spec carries no separate schema) |
| canonical audit reading (0A no result; REWORK bounded phase0_correction_max=3, first attempt free; then ESCALATE; BLOCKED/ESCALATE/FAIL per disposition; only 0F PASS starts product code) | 0C sec 13 | §17B, §60 | agree |
| ASK-UI: schemas K13, writer K06 | 0C sec 12 map | handoff | agree |
| RoutingDecision/Budget schemas K13, writers K04 | 0C sec 12 map | §28, §27A | agree |
| no other clashes | — | — | none |

## Coverage rows (K13 rows; all present)

M-D-D2: security records as bounded additive deltas; versioned migrations (§42). M-D-D4: auditor PASS only on full routed criteria; evidence refs persist (§21C, §21D; M-D-D4 check). M-D-D6: project + decision records atomic; unattributed actor anonymous (§8, §21B). M-D-D7: turn risk from stored contract; structured refusal with risk + ids (§25A; refusal carries risk + task/run ids). M-D-D33: repositories compose under one unit of work; atomic multi-record writes (§42 ports). M-D-D40: local compute via precheck + reserve + reconcile with leases (§38). cite: kit/BUILD_PLAN.md:1421-1439.
 B0B-UNCOVERED_BP04-36: TelemetryEvent envelopes + MetricRecords append-only; corrections are new records (§55). B0B-UNCOVERED_BP04-43: duplicate event_id returns the stored record, no duplicate (§55). cite: kit/BUILD_PLAN.md:1469-1470.
