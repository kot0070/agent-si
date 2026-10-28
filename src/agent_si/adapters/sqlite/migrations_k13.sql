-- =====================================================================
-- K13 storage migrations (Manifest §42 APPLICATION_STORAGE; §41 set).
--
-- BACKUP (run before applying, outside this script):
--   1. Stop writers (single-writer migration window), then copy the app
--      database file to a timestamped backup (e.g. agent_si.db ->
--      agent_si.db.bak-<utc-timestamp>) and record its sha256 next to it.
--   2. Keep the previous migration script beside the backup so the exact
--      applied schema version is recoverable without guessing.
--   3. Verify the backup opens read-only (PRAGMA quick_check) before
--      touching the live file.
--
-- VALIDATION (run after applying, before releasing writers):
--   1. PRAGMA foreign_key_check; PRAGMA integrity_check; both must be clean.
--   2. SELECT name FROM sqlite_master WHERE type='table' must include every
--      table below plus schema_migrations with one row per applied file.
--   3. Replay check: highest transition_sequence / run_sequence /
--      activation_sequence per scope must equal the pre-migration values
--      (stored state derives from committed sequences, never timestamps).
--   4. Application storage sweep test must pass:
--      tests/k13/test_storage_sweep.py (one-file run).
--
-- ROLLBACK (notes only; this script performs no destructive DDL):
--   1. Migrations are additive-only: CREATE TABLE IF NOT EXISTS, additive
--      columns, additive UNIQUE indexes. No destructive DDL in this script.
--   2. To roll back, stop writers and restore the pre-migration backup file;
--      never hand-delete tables to "undo" a migration.
--   3. If a later correction is needed, add a NEW migration that creates the
--      corrected shape; history rows are immutable and are never rewritten.
-- =====================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- §8 projects ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    workspace_root TEXT,
    default_director TEXT,
    default_manager_provider TEXT,
    default_manager_model TEXT,
    default_policies TEXT,
    budget_config TEXT,
    local_ai_config_ref TEXT,
    capability_db_ref TEXT,
    core_accounting TEXT NOT NULL DEFAULT 'ALWAYS_ON',
    diagnostic_telemetry_enabled INTEGER NOT NULL DEFAULT 0,
    sdk_tracing_enabled INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0
);

-- §13 task contracts (immutable; new version per change) -----------------
CREATE TABLE IF NOT EXISTS task_contracts (
    task_id TEXT NOT NULL,
    contract_version INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    contract_sequence INTEGER NOT NULL,
    contract_hash TEXT NOT NULL,
    project_id TEXT NOT NULL,
    parent_task_id TEXT,
    supersedes_task_id TEXT,
    phase_id TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT,
    priority TEXT,
    risk TEXT,
    goal TEXT,
    requirements TEXT,
    acceptance_criteria TEXT,
    inputs TEXT,
    outputs TEXT,
    workspace TEXT,
    permissions TEXT,
    tools TEXT,
    verification_policy_ref TEXT,
    audit_policy_ref TEXT,
    routing_policy_ref TEXT,
    retry_policy_ref TEXT,
    fallback_policy_ref TEXT,
    optimization_policy_ref TEXT,
    override_policy_ref TEXT,
    PRIMARY KEY (task_id, contract_version),
    UNIQUE (task_id, contract_sequence)
);

-- §15 contract activation records (immutable, authoritative) -------------
CREATE TABLE IF NOT EXISTS contract_activations (
    activation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    activation_sequence INTEGER NOT NULL,
    contract_version INTEGER NOT NULL,
    contract_sequence INTEGER NOT NULL,
    contract_hash TEXT NOT NULL,
    previous_contract_hash TEXT,
    amendment_id TEXT,
    effective_from TEXT,
    activation_reason TEXT,
    activated_at TEXT NOT NULL,
    evidence_refs TEXT,
    UNIQUE (task_id, activation_sequence)
);

-- §12 transition records (CAS + monotonic per-task sequence) -------------
CREATE TABLE IF NOT EXISTS task_transitions (
    transition_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    transition_sequence INTEGER NOT NULL,
    expected_from_state TEXT NOT NULL,
    expected_state_version INTEGER NOT NULL,
    new_state_version INTEGER NOT NULL,
    actor TEXT,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL,
    evidence_ref TEXT,
    suspended_from_state TEXT,
    resume_target_state TEXT,
    UNIQUE (task_id, transition_sequence),
    UNIQUE (task_id, new_state_version)
);

-- §14 execution runs -----------------------------------------------------
CREATE TABLE IF NOT EXISTS execution_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    run_sequence INTEGER NOT NULL,
    revision_no INTEGER NOT NULL DEFAULT 0,
    creation_reason TEXT,
    source_run_id TEXT,
    routing_decision_ref TEXT,
    routing_decision_refs TEXT,
    route TEXT,
    split_strategy TEXT,
    primary_provider TEXT,
    primary_provider_instance TEXT,
    primary_model TEXT,
    implementer_provider_ids TEXT,
    implementer_model_ids TEXT,
    status TEXT NOT NULL,
    termination_reason TEXT NOT NULL DEFAULT 'NONE',
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (task_id, run_sequence)
);

-- §14B execution attempts (immutable) ------------------------------------
CREATE TABLE IF NOT EXISTS execution_attempts (
    attempt_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    routing_assignment_id TEXT,
    attempt_no INTEGER,
    run_attempt_sequence INTEGER NOT NULL,
    attempt_type TEXT,
    provider TEXT,
    provider_instance TEXT,
    model TEXT,
    canonical_provider_id TEXT,
    canonical_model_id TEXT,
    output_artifact_refs TEXT,
    material_contribution INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    status TEXT NOT NULL,
    error_ref TEXT,
    usage_ref TEXT,
    input_ref TEXT,
    output_ref TEXT,
    retry_reason TEXT,
    fallback_reason TEXT,
    UNIQUE (run_id, run_attempt_sequence)
);

-- §15 amendments ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS amendments (
    amendment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    amendment_sequence INTEGER NOT NULL,
    scope TEXT,
    effective_from TEXT,
    target TEXT,
    change TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    source TEXT,
    status TEXT NOT NULL,
    UNIQUE (project_id, amendment_sequence)
);

-- §21B decision records ----------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_records (
    decision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    phase_id TEXT,
    gate_id TEXT,
    scope TEXT,
    type TEXT,
    statement TEXT,
    reason TEXT,
    authority TEXT,
    created_at TEXT NOT NULL,
    evidence_refs TEXT,
    supersedes_decision_id TEXT,
    status TEXT
);

-- §21A task packages (Director -> Manager bounded context) ----------------
CREATE TABLE IF NOT EXISTS task_packages (
    package_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    goal TEXT,
    context_refs TEXT,
    input_refs TEXT,
    requirements_ref TEXT,
    acceptance_criteria_refs TEXT,
    workspace TEXT,
    permissions_ref TEXT,
    tools_ref TEXT,
    routing_policy_ref TEXT,
    retry_policy_ref TEXT,
    fallback_policy_ref TEXT,
    optimization_policy_ref TEXT,
    verification_policy_ref TEXT,
    audit_policy_ref TEXT,
    override_policy_ref TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    invalidated_at TEXT,
    invalidation_reason TEXT,
    superseded_by_ref TEXT,
    hash TEXT
);

-- §21A agent tasks (Manager -> Agent bounded context) ----------------------
CREATE TABLE IF NOT EXISTS agent_tasks (
    agent_task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    subtask_id TEXT,
    run_id TEXT NOT NULL,
    agent_id TEXT,
    contract_hash TEXT NOT NULL,
    goal TEXT,
    context_refs TEXT,
    input_refs TEXT,
    acceptance_criteria_refs TEXT,
    workspace TEXT,
    permissions_ref TEXT,
    tools_ref TEXT,
    expected_outputs TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    invalidated_at TEXT,
    invalidation_reason TEXT,
    superseded_by_ref TEXT,
    hash TEXT
);

-- §21E task plans + planned subtasks --------------------------------------
CREATE TABLE IF NOT EXISTS task_plans (
    task_plan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    contract_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT,
    status TEXT NOT NULL,
    subtask_ids TEXT,
    dependency_edges TEXT,
    evidence_refs TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    hash TEXT
);

CREATE TABLE IF NOT EXISTS planned_subtasks (
    subtask_id TEXT PRIMARY KEY,
    task_plan_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    parent_subtask_id TEXT,
    goal TEXT,
    task_class TEXT,
    risk TEXT,
    required_capabilities TEXT,
    knowledge_needs TEXT,
    tool_needs TEXT,
    acceptance_criteria_refs TEXT,
    dependency_ids TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_compatibility_records (
    plan_compatibility_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    old_contract_hash TEXT NOT NULL,
    new_contract_hash TEXT NOT NULL,
    task_plan_id TEXT NOT NULL,
    result TEXT NOT NULL,
    checked_fields TEXT,
    evidence_refs TEXT,
    created_at TEXT NOT NULL
);

-- Phase0 work records -------------------------------------------------------
CREATE TABLE IF NOT EXISTS phase0_work_records (
    phase0_work_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    gate_id TEXT,
    artifact_id TEXT,
    artifact_hash TEXT,
    producer_role TEXT,
    producer_provider TEXT,
    producer_model TEXT,
    context_session_ref TEXT,
    created_at TEXT NOT NULL,
    source_refs TEXT,
    status TEXT NOT NULL
);

-- §21C verification records (immutable) ------------------------------------
CREATE TABLE IF NOT EXISTS verification_records (
    verification_id TEXT PRIMARY KEY,
    verification_sequence INTEGER NOT NULL,
    supersedes_verification_id TEXT,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    subtask_id TEXT,
    run_id TEXT NOT NULL,
    verification_scope_id TEXT NOT NULL,
    verification_target_type TEXT NOT NULL,
    attempt_id TEXT,
    attempt_ids TEXT,
    artifact_refs TEXT,
    contract_hash TEXT NOT NULL,
    criterion_results TEXT,
    result TEXT NOT NULL,
    handling_disposition TEXT,
    failure_class TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    evidence_refs TEXT,
    UNIQUE (verification_scope_id, verification_sequence)
);

-- §17B audit records + audit execution records ------------------------------
CREATE TABLE IF NOT EXISTS audit_records (
    audit_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    verification_ref TEXT,
    contract_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    handling_disposition TEXT,
    context_integrity TEXT,
    created_at TEXT NOT NULL,
    auditor_ref TEXT,
    evidence_refs TEXT
);

CREATE TABLE IF NOT EXISTS audit_execution_records (
    audit_execution_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    audit_id TEXT,
    started_at TEXT,
    ended_at TEXT,
    status TEXT NOT NULL,
    evidence_refs TEXT
);

-- §46 incident records (index only) ------------------------------------------
CREATE TABLE IF NOT EXISTS incident_records (
    incident_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    actor TEXT,
    detected_by TEXT,
    severity TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    root_cause TEXT,
    impact TEXT,
    action TEXT,
    regression_test TEXT,
    status TEXT
);

-- §45A context integrity records ----------------------------------------------
CREATE TABLE IF NOT EXISTS context_integrity_records (
    context_event_id TEXT PRIMARY KEY,
    incident_ref TEXT,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    actor TEXT,
    detected_by TEXT,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    expected_context_refs TEXT,
    actual_context_refs TEXT,
    missing_refs TEXT,
    conflicting_refs TEXT,
    contract_hash TEXT,
    detected_at TEXT NOT NULL,
    impact TEXT,
    resolution TEXT,
    resolved_at TEXT,
    evidence_refs TEXT
);

-- §12 suspension records + late-result reconciliations -------------------------
CREATE TABLE IF NOT EXISTS suspension_records (
    suspension_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    attempt_id TEXT,
    source_task_state TEXT,
    reason TEXT,
    started_at TEXT NOT NULL,
    resolved_at TEXT,
    run_suspension_state TEXT NOT NULL DEFAULT 'NONE',
    late_result_disposition TEXT,
    evidence_refs TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS late_result_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    attempt_id TEXT,
    suspension_id TEXT,
    late_output_refs TEXT,
    decision TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    reason TEXT,
    verification_ref TEXT,
    evidence_refs TEXT
);

-- §11 metric records (immutable) + pricing snapshots ---------------------------
CREATE TABLE IF NOT EXISTS metric_records (
    metric_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    metric_name TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT NOT NULL,
    state TEXT NOT NULL,
    source TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_snapshots (
    pricing_snapshot_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    source TEXT NOT NULL,
    input_token_price TEXT,
    output_token_price TEXT,
    cached_token_price TEXT,
    reasoning_token_price TEXT,
    request_price TEXT,
    other_rules TEXT,
    created_at TEXT NOT NULL,
    hash TEXT
);

-- §55 telemetry events (append-only envelopes) ----------------------------------
CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    attempt_id TEXT,
    subtask_id TEXT,
    parent_id TEXT,
    role TEXT,
    task_class TEXT,
    risk TEXT,
    state TEXT,
    route TEXT,
    split_strategy TEXT,
    provider TEXT,
    model TEXT,
    provider_instance TEXT,
    event_type TEXT NOT NULL,
    retry TEXT,
    verification_ref TEXT,
    audit_ref TEXT,
    re_execution TEXT,
    error_ref TEXT,
    fallback_reason TEXT,
    capability_rule TEXT,
    capability_evidence_ref TEXT,
    routing_decision_ref TEXT,
    routing_snapshot_id TEXT,
    resource_state_ref TEXT,
    metric_refs TEXT,
    final_status TEXT
);

-- §16 rework + fallback counters (atomic, restart-safe) --------------------------
CREATE TABLE IF NOT EXISTS rework_counter_records (
    counter_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    counter_type TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    counter_limit INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (scope_type, scope_id, counter_type)
);

CREATE TABLE IF NOT EXISTS fallback_counter_records (
    counter_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    counter_limit INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (scope_type, scope_id)
);

-- §17 fallback records ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fallback_records (
    fallback_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    source_run_id TEXT,
    replacement_run_id TEXT,
    source_attempt_id TEXT,
    reason TEXT NOT NULL,
    from_provider TEXT,
    from_model TEXT,
    to_provider TEXT,
    to_model TEXT,
    policy_ref TEXT,
    evidence_ref TEXT
);

-- §18B override records + override policies -----------------------------------------
CREATE TABLE IF NOT EXISTS override_records (
    override_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    authorized_by TEXT NOT NULL,
    authorization_ref TEXT,
    original_result TEXT,
    override_source_state TEXT,
    override_reason TEXT,
    override_action TEXT,
    accepted_risks TEXT,
    evidence_refs TEXT,
    scope TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS override_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    supersedes_policy_ref TEXT,
    accepted_risk_allowed INTEGER NOT NULL DEFAULT 0,
    allowed_source_states TEXT,
    non_overridable_failure_classes TEXT,
    non_overridable_ac_types TEXT,
    non_overridable_gate_ids TEXT,
    required_authority TEXT,
    post_override_rules TEXT,
    evidence_requirements TEXT,
    PRIMARY KEY (policy_id, version)
);

-- §28 routing decisions + assignments + evidence snapshots ------------------------------
CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    routing_snapshot_id TEXT NOT NULL,
    routing_policy_ref TEXT,
    optimization_policy_ref TEXT,
    retry_policy_ref TEXT,
    fallback_policy_ref TEXT,
    verification_policy_ref TEXT,
    audit_policy_ref TEXT,
    override_policy_ref TEXT,
    candidate_models TEXT,
    candidate_providers TEXT,
    selected_provider TEXT,
    selected_model TEXT,
    routing_assignment_ids TEXT,
    route TEXT,
    strategy TEXT,
    reason TEXT,
    eligibility_source TEXT,
    capability_state TEXT,
    required_verification TEXT,
    eligibility_branch_evidence_refs TEXT,
    capability_evidence_refs TEXT,
    provider_health_ref TEXT,
    model_health_ref TEXT,
    resource_state_ref TEXT,
    risk_override TEXT,
    estimated_cost TEXT,
    estimated_latency TEXT,
    optimization_score TEXT,
    fallback_chain TEXT
);

CREATE TABLE IF NOT EXISTS routing_assignments (
    assignment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    subtask_id TEXT,
    role TEXT,
    stage TEXT,
    route TEXT,
    provider TEXT,
    provider_instance TEXT,
    model TEXT,
    capability_evidence_refs TEXT,
    resource_state_ref TEXT,
    budget_reservation_ref TEXT,
    routing_policy_ref TEXT,
    optimization_policy_ref TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_evidence_snapshots (
    routing_snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    provider_health_snapshot TEXT,
    model_health_snapshot TEXT,
    resource_state_snapshot TEXT,
    budget_state_snapshot TEXT,
    candidate_snapshot TEXT,
    policy_versions TEXT,
    capability_evidence_refs TEXT,
    hash TEXT
);

-- §38 resource state snapshots + leases + reservations ------------------------------------
CREATE TABLE IF NOT EXISTS resource_state_snapshots (
    resource_state_snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL,
    available_gpu_slots INTEGER,
    available_cpu_slots INTEGER,
    memory_available TEXT,
    gpu_memory_available TEXT,
    queue_depth INTEGER,
    provider_capacity_refs TEXT,
    hash TEXT
);

CREATE TABLE IF NOT EXISTS resource_leases (
    lease_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    owner_run_id TEXT,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    released_at TEXT,
    status TEXT NOT NULL,
    capacity_claim TEXT,
    evidence_ref TEXT
);

CREATE TABLE IF NOT EXISTS resource_reservations (
    reservation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    owner_run_id TEXT,
    requested_capacity TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    fulfilled_at TEXT,
    released_at TEXT,
    status TEXT NOT NULL,
    evidence_ref TEXT
);

-- §28/§25A/§26A policy objects (immutable, versioned) ---------------------------------------
CREATE TABLE IF NOT EXISTS routing_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    task_class TEXT,
    risk_level TEXT,
    strict_min TEXT,
    tolerant_min TEXT,
    confidence_min TEXT,
    sample_min TEXT,
    freshness_requirement TEXT,
    local_allowed INTEGER NOT NULL DEFAULT 0,
    split_allowed INTEGER NOT NULL DEFAULT 0,
    cloud_required INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS optimization_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    required_quality TEXT,
    max_risk TEXT,
    weight_quality TEXT,
    weight_cost TEXT,
    weight_latency TEXT,
    weight_cloud_tokens TEXT,
    local_preference TEXT,
    deadline TEXT,
    budget_limit TEXT,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS retry_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    executor_attempt_max INTEGER NOT NULL DEFAULT 3,
    provider_retry_max INTEGER NOT NULL DEFAULT 2,
    format_retry_max INTEGER NOT NULL DEFAULT 1,
    verification_retry_max INTEGER NOT NULL DEFAULT 1,
    audit_correction_max INTEGER NOT NULL DEFAULT 2,
    verification_correction_max INTEGER NOT NULL DEFAULT 2,
    runtime_correction_max INTEGER NOT NULL DEFAULT 3,
    backoff_policy TEXT,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS fallback_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    allowed_reasons TEXT,
    fallback_chain TEXT,
    same_run_rules TEXT,
    new_run_rules TEXT,
    max_fallbacks_per_run INTEGER,
    max_fallbacks_per_task INTEGER,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS verification_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    requirement TEXT NOT NULL,
    required_types TEXT,
    retry_policy_ref TEXT,
    evidence_requirements TEXT,
    failure_disposition_policy_ref TEXT,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS audit_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    audit_requirement TEXT NOT NULL,
    minimum_independence_level TEXT,
    required_context_integrity TEXT,
    retry_policy_ref TEXT,
    override_policy_ref TEXT,
    manual_review_rules TEXT,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS failure_disposition_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL,
    supersedes_policy_ref TEXT,
    failure_class_rules TEXT,
    severity_rules TEXT,
    retry_policy_ref TEXT,
    fallback_policy_ref TEXT,
    override_policy_ref TEXT,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS policy_lifecycle_records (
    policy_lifecycle_id TEXT PRIMARY KEY,
    policy_ref TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    lifecycle_sequence INTEGER NOT NULL,
    event TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT,
    supersedes_policy_ref TEXT,
    UNIQUE (policy_id, lifecycle_sequence)
);

-- §19A authorization records + action executions ----------------------------------------------
CREATE TABLE IF NOT EXISTS authorization_records (
    authorization_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    risk_level TEXT,
    action TEXT NOT NULL,
    scope TEXT,
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    expires_at TEXT,
    evidence_ref TEXT
);

CREATE TABLE IF NOT EXISTS action_executions (
    action_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    idempotency_key TEXT NOT NULL,
    authorization_ref TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    external_ref TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (idempotency_key)
);

-- §27A budget states + reservations + settlements -------------------------------------------------
CREATE TABLE IF NOT EXISTS budget_states (
    project_id TEXT PRIMARY KEY,
    currency TEXT NOT NULL,
    budget_limit TEXT,
    soft_limit TEXT,
    hard_limit TEXT,
    spent TEXT NOT NULL DEFAULT '0',
    reserved TEXT NOT NULL DEFAULT '0',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_reservations (
    reservation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    estimated_amount TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    expires_at TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_settlements (
    settlement_id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    provider_usage_evidence_ref TEXT,
    provider_request_ref TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    actual_amount TEXT,
    difference TEXT,
    status TEXT NOT NULL,
    settled_at TEXT,
    source TEXT,
    UNIQUE (reservation_id, provider_usage_evidence_ref)
);

-- §37 capability evidence + provider/model contracts + usage reporting -------------------------------
CREATE TABLE IF NOT EXISTS capability_evidence (
    evidence_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_id TEXT,
    model_id TEXT,
    task_class TEXT,
    status TEXT,
    measured_at TEXT,
    source TEXT NOT NULL,
    details_ref TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS provider_contracts (
    provider_contract_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    capabilities TEXT,
    health TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    hash TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_contracts (
    model_contract_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    capabilities TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    hash TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_reporting_capabilities (
    capability_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    usage_reporting_supported INTEGER NOT NULL DEFAULT 0,
    probed_at TEXT,
    evidence_ref TEXT
);

-- §21 governance artifacts ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS governance_artifacts (
    artifact_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    phase0_work_id TEXT,
    project_id TEXT NOT NULL,
    hash TEXT NOT NULL,
    hash_algorithm TEXT NOT NULL DEFAULT 'sha256',
    created_at TEXT NOT NULL,
    approved_by TEXT,
    source TEXT,
    PRIMARY KEY (artifact_id, version)
);

-- §21D finalization records --------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS finalization_records (
    finalization_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    task_state TEXT NOT NULL,
    audit_ref TEXT,
    audit_result TEXT,
    completion_disposition TEXT NOT NULL,
    override_ref TEXT,
    verification_ref TEXT,
    output_refs TEXT,
    metric_refs TEXT,
    completed_at TEXT NOT NULL,
    limitations TEXT
);
