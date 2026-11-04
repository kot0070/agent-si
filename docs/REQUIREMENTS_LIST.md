# Requirements list

This is the full list behind the app: 437 requirement rows from the original build plan, grouped by work package. The 14 functions in the demo video are only the main ones. Not listed: the 6 rows of K01, which are rules for the build itself rather than things the app does.

How to read it:

- Each row is what the build plan asked for, in its own short words. Some rows are about the build and its proofs rather than a screen in the app.
- In the plan's own table every row is marked DEFAULT, the status its acceptance step sets for work proven on the default path. Those marks were set during the build. The table was last changed on November 1, before the last fixes.
- The rows were not rechecked one by one on the release build. Testing by hand after that date still found defects, so read these marks as the build's own record, not as a fresh proof. Where this page and [Known issues](KNOWN_ISSUES.md) differ, Known issues is right.

## K02: Hierarchy and orchestration: Director, Managers, workers (62)

| Row | Requirement |
|---|---|
| 22 | control-plane mapping documented |
| 32 | largest parallel decomposition up to the cap, rest queued |
| 33 | served part register, not a markdown file |
| 35 | ledger report nudge for the next package |
| 87 | served phase gate; no next phase until CLOSE |
| 93 | opt-in split into N disjoint parts, N parallel Managers |
| 94 | each part has its own gate plus fresh audit |
| 95 | integration Manager assembles; phase closes after its PASS |
| 96 | frozen interface manifest with hash checked in part validation |
| 100 | product split with bounded context per Manager |
| 101 | overlap starts only on refs resolved to gate plus audit PASS |
| 102 | link-check Manager verifies joints |
| 103 | hierarchy settings changes persist a decision row |
| 116 | clarification opens a bounded delta package |
| 117 | non-blocking delta runs in parallel with link-check close |
| 118 | open packages and gates cross-checked at gate evaluation |
| B0B-BP01-10 | TaskPlanner decompose is idempotent on package ref and goal hash via the existing plan ref. |
| B0B-BP01-65 | rejects overlapping agent scopes with REJECTED_SCOPE_OVERLAP citing the conflict. |
| B0B-BP01-72 | rejects overlapping decomposition part scopes before fan-out. |
| B0B-BP01-73 | blocks parent closure when the required integration task is missing after parts PASS. |
| B0B-BP03-4 | sets the SDK client retry limit to max_retries=0 and performs runner retries only through RoutingDec |
| B0B-SDK-132 | limits architecture conclusions to the verified SDK surface. |
| B0B-UNCOVERED_ARCH-456 | Give every agent a distinct non-overlapping scope; duplicated agent scopes violate fan-out control |
| B0B-UNCOVERED_ARCH-461 | Keep planning and routing layers subordinate to the Manager-to-Agents hierarchy; the Manager retains |
| B0B-UNCOVERED_ARCH-57 | uses Chat Completions for non-OpenAI providers and never assumes Responses API |
| B0B-UNCOVERED_ARCH-7 | An AgentTask without subtask_id is rejected at dispatch and only planned AgentTasks execute |
| B0B-UNCOVERED_ARCH-704 | Only the USER appends entries to the user corrections channel; Managers and agents read it read-only |
| B0B-UNCOVERED_ARCH-705 | A TaskPackage whose corrections hash mismatches the checked hash is rejected at issuance. |
| B0B-UNCOVERED_ARCH-755 | The Manager queues demand within capacity caps instead of dropping work. |
| B0B-UNCOVERED_ARCH-762 | A reached capacity cap queues newcomers with position and estimated start. |
| B0B-UNCOVERED_ARCH-766 | Every specialized Manager agent holds a distinct non-overlapping scope and deliverable without dupli |
| B0B-UNCOVERED_BP06-30 | Block activation on invalid hierarchy chain shapes without mutating stored configuration |
| B0B-UNCOVERED_BP06-68 | Treat contributor bindings as development-only and refuse production use |
| B0B-UNCOVERED_BP06-78 | Grant role authority only through configured role models and refuse unconfigured roles |
| B0B-UNCOVERED_BP06-81 | Route project work to roles through a defined project-to-role target flow |
| B0B-UNCOVERED_UI_DELTA-23 | emergency restoration rebinds each role to its configured RoleModelProfile while keeping completed a |
| B0B-UNCOVERED_UI_DELTA-36 | routes non-OpenAI providers through a generic OpenAI-compatible Chat Completions adapter configured |
| B0B-UNCOVERED_UI_DELTA-57 | Routine-work analysis and handoff to cheaper local or specialized executors MUST be switchable ON/OF |
| B0B-UNCOVERED_UI_DELTA-59 | supports a combined flow of project creation, hierarchy setting, pooled binding, offload toggle, pau |
| B0B-UNCOVERED_UI_DELTA-60 | records hierarchy, provider-binding, and offload-toggle changes with actor and timestamp, validates |
| B0B-UNCOVERED_UI_DELTA-62 | surfaces audit-independence and budget rejections to the user when applying hierarchy, binding, or t |
| LIVE0-07 | the OpenAPI and docs schema answer, no 500 |
| LIVE0B-02 | POST /api/v1/projects stores the chosen folder and GET returns it |
| LIVE0B-03 | a created project is written to disk and survives a restart |
| M-D-D13 | worker context isolated; listed shared inputs only when authorized |
| M-P1-10 | Manager fan-out bounded by scheduler caps; excess queues |
| M-P1-15 | part register as served rows; deps from gate plus audit PASS |
| M-P1-17 | per-package load visible; report nudge; no auto-push |
| M-P1-28 | routine handoff per-project switch; hand-overs recorded |
| M-P1-33 | stronger audit model only when needed; choice logged |
| M-P1-42 | no live provisional Director default; control-plane-only rule |
| M-P2-80 | governance folder HD-only; staged rows to hierarchy |
| M-P2-82 | staged requirement subset per inputs folder |
| M-R-GOV | governance raw reads Director-only; staged rows to hierarchy |
| MH-2 | each milestone/part gate carries a configurable verification threshold param (policy field + project setting + UI control); below-threshold milestone cannot PASS and triggers correction/escalation. |
| R-301 | team card in context; decomposition names the facts used |
| R-302 | real hierarchy: Director splits, tool agents run parts, Manager integrates |
| R-303 | team by task: sized and staffed per block with recorded WHY |
| R-333 | routine offloading with per-project switch, hand-overs recorded |
| R-349 | max agent steps per project, separate for chat |
| R-358 | every configuration change validated (independence, budget, caps) and recorded before it applies |
| R-359 | multi-Manager per-project settings; part-only context; dependency-graph scheduling; no hard-wired pattern |

## K03: Assurance, the QA catalog and the test stage (39)

| Row | Requirement |
|---|---|
| 7 | assurance on every served turn; empty work fails |
| 9-13 | fresh auditor instance per audit and re-audit |
| 13 | pair reuse needs a recorded decision plus user visibility |
| 199 | PASS only after assertion; auditor checks versus plan |
| 200 | catalog versions plus change log plus proposal approval flow |
| 201 | runner contract plus user-runner approval |
| 246 | test-stage proof filed in the acceptance run |
| B0B-BP07-14 | performs fail-closed audit sourcing that emits BLOCKED when no auditor is eligible and offers config |
| B0B-BP07-17 | keeps audit sourcing fail-closed and emits BLOCKED when auditor sourcing cannot complete. |
| B0B-BP07-18 | emits BLOCKED for audit sourcing when no eligible auditor exists and prohibits PASS until sourcing s |
| B0B-BP07-20 | returns NO_ELIGIBLE_AUDITOR from the auditor registry, emits BLOCKED at the gate, and prohibits PASS |
| B0B-BP07-53 | gates auditor sourcing on an explicit USER decision and keeps sourcing fail-closed until the user re |
| B0B-BP07-54 | keeps audit sourcing fail-closed BLOCKED until the USER resolves auditor provider options. |
| B0B-SDK-104 | defines machine-verifiable deliverable schemas. |
| B0B-SDK-107 | checks semantic architecture and security criteria beyond schema validity. |
| B0B-SDK-109 | handles turn-cap refusal and invalid-output errors through named handlers. |
| B0B-UNCOVERED_ARCH-622 | A missing evidence reference fails the criterion instead of passing silently. |
| B0B-UNCOVERED_ARCH-652 | An auditor candidate with missing capability evidence stays ineligible until evidence arrives. |
| B0B-UNCOVERED_ARCH-653 | No eligible auditor forces AuditResult BLOCKED instead of degraded self-audit. |
| B0B-UNCOVERED_ARCH-654 | L2 separate-model holds only when the auditor canonical model id stays absent from implementer model |
| B0B-UNCOVERED_ARCH-740 | The product runtime sources independent auditors; auditor sourcing is independent of implementers. |
| B0B-UNCOVERED_ARCH-741 | Audit sourcing for the auditor task class fails closed to AuditResult BLOCKED when no auditor is eli |
| B0B-UNCOVERED_ARCH-745 | No eligible auditor yields BLOCKED with the Task parked until the USER resolves sourcing. |
| B0B-UNCOVERED_ARCH-746 | Missing auditor capability evidence marks the candidate ineligible. |
| B0B-UNCOVERED_MVP_ACCEPT-111 | verification and audit confirm the recovery leg before a run is accepted as recovered. |
| B0B-UNCOVERED_MVP_ACCEPT-117 | audit rework is bounded by the audit correction budget and every re-audit uses a fresh auditor. |
| B0B-UNCOVERED_MVP_ACCEPT-224 | unresolved auditor-provider dependency fails closed to BLOCKED with documented options. |
| B0B-UNCOVERED_MVP_ACCEPT-33 | AttemptExecutionGate and DeterministicVerify classify each failure into its canonical failure class |
| M-P1-41 | close each stage with its audit; every close leaves a queryable row |
| M-P3-120 | four built-in test bases plus attached; CODE-AI-HUMAN kinds |
| M-P4-154 | local tests default ON globally; per-project switch; TESTS view |
| M-P4-155 | TEST stage: catalog plan; one permission dialog each; run view |
| M-R-REAL-API | provider-facing code tested at once via gateway; recorded spend; ask near cap |
| MH-4 | verifier/auditor role executes with read-only tools only (guard-enforced; write attempt rejected); audit record proves producer set ∩ auditor = empty and verifier write set = empty. |
| R-304 | auditor judges the real files read and written |
| R-338 | tests only from the catalog (896); named ladder rungs before HUMAN |
| R-347 | local tests = one switch; Tests tab informational |
| R-355 | every PASS result audited by a new fresh auditor; contributors never auditors; accepted risk off by default, user-only |
| R-368 | test plan from the catalog, execution kinds summing to the total, status rules, runner contract, ladder asked once |

## K04: Providers, routing, model knowledge and the budget (94)

| Row | Requirement |
|---|---|
| 42 | no baked-in vendor default; fresh install blocks with a reason |
| 43 | pinned swaps only through the recorded fallback path |
| 67 | served default matches the stated multi-model strategy |
| 208 | KB task fit plus quality fields feed the served scorer |
| 255 | one-click offers the strongest text/tools/coding model from the KB |
| 256 | AUTO routes on task plus price plus quality, never by alphabet |
| B0B-BP02-8 | routing performs selection only. |
| B0B-BP02-9 | routing never invokes provider SDKs. |
| B0B-BP03-17 | surfaces a provider 5xx or timeout as a FAILED ExecutionAttempt carrying error_ref and never silentl |
| B0B-BP03-18 | records a max-turns trip as a FAILED ExecutionAttempt with an explicit reason. |
| B0B-BP03-9 | performs runner retries only from RoutingDecision-bound RunConfig with client max_retries=0 and post |
| B0B-BP07-44 | verifies local model identities and instances through dedicated local-output verification. |
| B0B-SDK-111 | records turn-cap configuration in the routing decision. |
| B0B-SDK-114 | schedules runner retries only under an explicit retry policy. |
| B0B-SDK-116 | treats default client retries as hidden recovery. |
| B0B-SDK-123 | reaches the Meta cloud endpoint through a secret reference. |
| B0B-SDK-124 | records the Meta provider endpoint and model catalogue in its provider contract. |
| B0B-SDK-17 | supports per-run model provider override through routing. |
| B0B-SDK-32 | disables hidden client retries so retry policy owns recovery. |
| B0B-SDK-79 | binds canonical model identity at dispatch from agent and run configuration. |
| B0B-UNCOVERED_ARCH-164 | Health displays show MEASURED versus UNAVAILABLE honestly with probe-backed matrices |
| B0B-UNCOVERED_ARCH-294 | Treat local model tag presence as presence only; never as capability evidence; capability needs meas |
| B0B-UNCOVERED_ARCH-303 | Treat a provider without an evidenced credential as ineligible for routing; never route on an absent |
| B0B-UNCOVERED_ARCH-412 | Derive estimated_tokens from request max_tokens plus policy overhead |
| B0B-UNCOVERED_ARCH-416 | Reserve budget only through reserveTokens; never invent currency amounts |
| B0B-UNCOVERED_ARCH-424 | Accept new prices only as new immutable PricingSnapshot versions |
| B0B-UNCOVERED_ARCH-427 | Route recoverable budget blocks to BLOCKED where top-up can restore and to ESCALATED otherwise |
| B0B-UNCOVERED_ARCH-441 | Compensate failed gates idempotently to RELEASED and persist the compensation_ref |
| B0B-UNCOVERED_ARCH-452 | Probe local usage capability only with permission; unpermitted local probing is a violation |
| B0B-UNCOVERED_ARCH-527 | The AI SETTINGS Models view presents stored model contracts together with runtime health for every c |
| B0B-UNCOVERED_ARCH-528 | The AI SETTINGS Optimization Policy view presents required quality and risk ceiling and weights and |
| B0B-UNCOVERED_ARCH-681 | Cost figures arrive only through CostCalculator calculation over PricingSnapshot evidence. |
| B0B-UNCOVERED_ARCH-726 | High-risk reasoning and final verification run on measured capable candidates; unmeasured cheap or l |
| B0B-UNCOVERED_ARCH-753 | Provider clients use max_retries 0 so every invocation is one authoritative ExecutionAttempt. |
| B0B-UNCOVERED_BP04-14 | A PricingSnapshot row referenced by calculated cost is immutable; corrections create a new snapshot |
| B0B-UNCOVERED_BP04-34 | A pre-run BUDGET_BLOCKED with billable execution already started terminalizes the run as BUDGET_BLOC |
| B0B-UNCOVERED_BP04-5 | Re-collection with an identical usage reference attaches to the existing MetricRecord without duplic |
| B0B-UNCOVERED_BP04-67 | Metric rows lacking value or unit or state or source are rejected at write time |
| B0B-UNCOVERED_BP04-8 | Every budget breach is recorded as a persistent incident record; no breach is resolved silently |
| B0B-UNCOVERED_BP05-14 | The provider registry MUST hold transport descriptors plus per-instance health plus per-adapter usag |
| B0B-UNCOVERED_BP05-81 | MUST provide a LiteLLM-backed adapter with recorded limits and route params and usage probes. |
| B0B-UNCOVERED_BP06-72 | Serve mock provider routes until the USER supplies a key and mark mocked traffic as mock |
| B0B-UNCOVERED_MVP_ACCEPT-168 | L3 independent audit may use a separate cloud provider with its own key. |
| B0B-UNCOVERED_MVP_ACCEPT-219 | provider matrix records only evidenced credentials; unevidenced endpoints stay unproven. |
| B0B-UNCOVERED_MVP_ACCEPT-228 | split demo cloud leg uses the evidenced cloud credential. |
| B0B-UNCOVERED_MVP_ACCEPT-52 | SPLIT RoutingDecisions carry the local_draft and cloud_verify assignments atomically. |
| B0B-UNCOVERED_UI_DELTA-17 | TARGET_FLOW resolves every role model from configuration with no hard-coded role default. |
| B0B-UNCOVERED_UI_DELTA-30 | AI SETTINGS in AGENT_SI exposes per-role editing of RoleModelProfile mode, provider, and model, incl |
| B0B-UNCOVERED_UI_DELTA-31 | AI SETTINGS role edits to mode, provider, or model persist and reflect in the stored profiles. |
| B0B-UNCOVERED_UI_DELTA-32 | confirms stored role profiles and subsequent run behavior reflect AI SETTINGS edits. |
| B0B-UNCOVERED_UI_DELTA-33 | The agent_si development model binding applies only to the product development process and never act |
| B0B-UNCOVERED_UI_DELTA-34 | verifies no role falls back to muse-spark without an explicit user PINNED choice and no vendor or mo |
| B0B-UNCOVERED_UI_DELTA-39 | provides a LiteLLM-backed adapter for providers without an OpenAI-compatible API and records probed |
| B0B-UNCOVERED_UI_DELTA-4 | allows a Manager role model change only with a recorded canonical reason and rejects an unjustified |
| B0B-UNCOVERED_UI_DELTA-40 | lists a litellm-backed entry in the adapter registry for routes without an OpenAI-compatible API |
| B0B-UNCOVERED_UI_DELTA-41 | probes each non-OpenAI-compatible route and records its limits and route parameters |
| B0B-UNCOVERED_UI_DELTA-55 | reads back stored bindings and lists all pool members with declared use mode for each role |
| HD-PROVIDERS | named provider presets (Claude, Gemini, Mistral, Groq, OpenRouter, DeepSeek, xAI) by config |
| LIVE0B-06 | GET /api/v1/budget answers the project budget so the Tasks page loads, no 404 on the listed route |
| M-D-D14 | non-default Manager model only via FallbackRecord; ledger binds provider |
| M-D-D21 | every real-API and real local-AI run through provisioning gateway |
| M-D-D26 | routing plus budget duties as owned port roles |
| M-D-D28 | one routing per run via stored profiles; no eligible profile blocks |
| M-P1-23 | generic adapters; provider-specific leg per provider |
| M-P1-25 | one recorded live E2E on non-Meta non-OpenAI provider for MVP |
| M-P2-63 | billed spend per trial vs monthly cap; warn plus block |
| M-P3-124 | shipped model KB format; AUTO reads fit-price-quality |
| M-P4-144 | leftover-key finder lists product-prefixed entries; user-click delete |
| M-P4-145 | finder shows names plus dates only; never touches others |
| M-P4-146 | live-provider-linked entry never deletable |
| M-P4-147 | explicit confirm per entry and behind session token |
| M-P4-148 | credential deletion audit-logged by entry name; real reasons |
| M-P4-149 | in-repo tests use fakes; real-store smoke via gateway |
| M-R-ANY-API | any API provider via base-url plus model plus secret; LiteLLM path; probes stay |
| M-R-LEFTOVER | leftover-key finder: own-prefix only; per-entry confirm plus journal |
| M-R-MODEL-KB | model KB in named format with schema plus manifest plus version |
| M-R-SIMPLE | mini multi-provider run AUTO at every level with why-text |
| M-R-UX-13 | model store search on top; provider groups; per-model toggle |
| R-305 | exact assigned model id; visible allow-list fallbacks |
| R-306 | mixed-provider hierarchy proven by the acceptance mini-drive |
| R-307 | providers verified on distinct levels |
| R-308 | cheapest optimal model per block from the KB |
| R-309 | KB holds every model the accounts offer or UNKNOWN |
| R-310 | not-in-base mark consistent at every choice point |
| R-311 | editable budget counts real usage; block says so in words |
| R-332 | OpenAI Agents SDK engine (K02); provider presets incl. LM Studio; per-role pinned / pool / AUTO |
| R-339 | provider catalog, key-only connect, model checkboxes + search, chat selector, Disconnect, closable dialogs |
| R-340 | in-app model KB fields, connected-only read, Update + last date, AI refresh as proposal |
| R-344 | key save never hangs, dialogs close, Disconnect works, stable provider list |
| R-346 | key delete removes the credential-store entry; safe leftover finder |
| R-356 | no built-in vendor or model default for any role; the development model is never a product default |
| R-357 | every model choice recorded with its reason in telemetry; plain-language pool strategy per level in a guided picker |
| R-369 | single-provider mode works fully (K03 audits on fresh context with recorded acceptance); multi-provider auditor differs |
| R-370 | model KB per-field source and date, UNKNOWN unsourced, updater as user-applied proposal with change log |

## K05: Local AI (40)

| Row | Requirement |
|---|---|
| 111 | local-AI settings with per-change decision record (backend: settings routes, decision record store) |
| B0B-BP02-63 | admits a local candidate for any role level only with capability tier evidence plus health plus gate |
| B0B-BP02-68 | admits a local candidate only with tier PROXY or MEASURED plus health plus gateway permission. |
| B0B-BP02-77 | treats missing permission health or gateway metadata as INELIGIBLE with reason. |
| B0B-BP02-88 | admits local candidates only with tier evidence plus health plus gateway permission; local-only mode |
| B0B-BP03-47 | attaches and starts an on-demand local helper through the gateway for a routed assignment and releas |
| B0B-UNCOVERED_ARCH-189 | ResourceScheduler queues excess demand under technical caps instead of dropping work |
| B0B-UNCOVERED_ARCH-352 | Contact local endpoints only with permission; unpermitted local endpoint contact is a violation |
| B0B-UNCOVERED_ARCH-367 | Refresh stale capability copies with versions; never use stale copies as current evidence |
| B0B-UNCOVERED_ARCH-373 | Consume prose capability notes only through a labelled PROXY adapter; never as direct numeric scores |
| B0B-UNCOVERED_ARCH-767 | Host and process and API and scheduling safety caps are non-count limits; the Manager queues further |
| B0B-UNCOVERED_BP05-29 | Local discovery MUST reject permission-less probing at the discovery gate and the identity MUST stay |
| B0B-UNCOVERED_BP05-65 | When gateway preconditions are unmet the local adapter contract MUST record a violation and refuse c |
| B0B-UNCOVERED_BP05-70 | Local configurations MUST be scoped by project key so one project cannot read another project local |
| B0B-UNCOVERED_BP05-92 | The local adapter contract MUST derive UNKNOWN or PROXY or MEASURED tiers from recorded evidence and |
| B0B-UNCOVERED_BP05-94 | MUST normalize agent_ops.db notes as PROXY with threshold and shape UNKNOWN until fresh benchmark ev |
| B0B-UNCOVERED_BP06-44 | Require local_ai_allowed at every used level when local_only_mode is set and validate local identiti |
| B0B-UNCOVERED_BP06-48 | Block activation without mutating stored configuration when local_only_mode is true and any used lev |
| B0B-UNCOVERED_MVP_ACCEPT-175 | local eligibility branch A requires numeric capability evidence before use. |
| B0B-UNCOVERED_MVP_ACCEPT-181 | local endpoint, model, and permission settings persist via LocalAIConfig only. |
| B0B-UNCOVERED_MVP_ACCEPT-19 | cloud verifier record references the draft artifact hash and records re-examination of the draft con |
| B0B-UNCOVERED_MVP_ACCEPT-221 | non-running local runtimes keep UNKNOWN capability and grant no eligibility. |
| B0B-UNCOVERED_MVP_ACCEPT-222 | capability store without evidence columns yields UNKNOWN for local classes. |
| B0B-UNCOVERED_MVP_ACCEPT-223 | role config fields are not capability task classes. |
| B0B-UNCOVERED_MVP_ACCEPT-50 | SplitPlanner local_draft plus cloud_verify assignments carry dependency ordering and dual provenance |
| B0B-UNCOVERED_MVP_ACCEPT-53 | verifier input binds the draft artifact hash so cloud verification is traceable to the exact draft o |
| B0B-UNCOVERED_MVP_ACCEPT-57 | cloud verifier input references the draft artifact hash and verification confirms the link. |
| M-D-D10 | capability knowledge refreshed read-only; original untouched |
| M-D-D15 | offline probe envs separate from product infra; offline only |
| M-D-D16 | stale knowledge copies kept as backups; owner questions close gates |
| M-D-D22 | capability knowledge read-only; local tests after passive checks |
| M-D-D41 | fail closed before external contact when host checks fail |
| M-P4-129 | benchmark results steer cloud-vs-local splits; deeper levels |
| M-P4-130 | owner benchmark originals read-only; suite may grow |
| M-P4-132 | benchmark level durations 5-15-30 min; equal wall-clock meaning |
| M-P4-133 | real local-model runs only via gateway; fakes in tests; LOCAL-ONLY zero cloud |
| R-312 | local runtimes connected and used as tool agents |
| R-341 | benchmark path -> scan -> level -> run, warnings, size-scaled levels, feeds capability base (backend: routes, scan, run, store) |
| R-360 | local-AI safety: passive check, skip when busy, no pulls or deletes, capability evidence recorded |
| R-371 | benchmark hardware/runtime detection, calibration, PROXY vs MEASURED with hardware profile |

## K06: The tool belt, permissions and services (19)

| Row | Requirement |
|---|---|
| 189 | contract plus template plus instruction text in UI/docs |
| 195 | detected environment plus per-project merge, served test |
| 252 | full tool-belt chain demo as run evidence |
| 253 | declared-services acceptance run filed |
| 254 | install-record view test |
| B0B-UNCOVERED_MVP_ACCEPT-141 | environment example lists required keys with empty or placeholder values and SecretRef pointers. |
| B0B-UNCOVERED_MVP_ACCEPT-88 | guardrail check blocks retrieved instruction override and records the block with its evidence. |
| B0B-UNCOVERED_MVP_ACCEPT-93 | guardrail records show allow-with-containment or block as designed with the evidence refs. |
| M-D-D3 | port contracts frozen by hash; targets pinned per allow |
| M-D-D36 | action execution persisted; prior external state verified before repeat |
| M-D-D51 | channel evaluation persisted before socket use; fail-closed, no deadlock |
| M-D-D8 | tools only via registry plus guarded dispatcher in every adapter |
| MH-1 | after retry/correction budget exhaustion the run parks as ESCALATED and the user gets an in-product escalation card (reason, evidence refs, resume/discard) in chat and run view; no silent park. |
| MH-3 | any tool call outside the task-authorized list is deterministically rejected (named error code, guard record, no execution/side effect) on the production path. |
| R-313 | approval card in chat; sessions listed after restart |
| R-314 | ASK buttons in chat and run view; click resumes |
| R-315 | plain chat writes files through offered tools |
| R-365 | imported scripts: contract, validation, sandbox dry-run, approval, hash pin, no keys or network, never shadow |
| R-367 | portable scripts: declared parameters, UNKNOWN not alarms, detected-environment page, check-on-this-PC, environment matrix |

## K07: The shell, UX, cards and languages (61)

| Row | Requirement |
|---|---|
| 111-UI | local-AI settings view: each change made in the UI, its decision record shown (over the K05 routes; HD 20:0x owner order) |
| 162 | comfort judged in the acceptance drive (row 166 run) |
| 163 | adopted-system decision recorded in docs |
| 168 | design and clarity sign-off inside the acceptance drive |
| 242 | no raw ids as primary content |
| 248 | card pattern parity across the app, both languages |
| B0B-BP09-27 | analytics views present optional breakdowns as optional and never as required presence. |
| B0B-BP09-30 | report export may attach derived narratives labelled DERIVED that never override measured records. |
| B0B-UNCOVERED_ARCH-526 | The AI SETTINGS Local AI view presents stored Local AI configuration plus the local endpoint and mod |
| B0B-UNCOVERED_ARCH-541 | The AGENT_SI console uses a chat-first layout with status panels and no graph editor canvas; product |
| B0B-UNCOVERED_ARCH-550 | The live agents view updates as agents start and finish without page reload. |
| B0B-UNCOVERED_ARCH-563 | ABBenchmarkRunner keeps repeatable cloud-only versus local-assisted arms on identical task class and |
| B0B-UNCOVERED_ARCH-643 | Final reports include DEMO and MVP acceptance evidence traced to authoritative stored records. |
| B0B-UNCOVERED_ARCH-679 | Presence of each named menu and view in the console is MUST. |
| B0B-UNCOVERED_ARCH-683 | Extended allocations beyond the named menus are derived display split from authoritative telemetry. |
| B0B-UNCOVERED_ARCH-686 | Treating a SHOULD breakdown as MUST presence or the reverse is a scope breach. |
| B0B-UNCOVERED_ARCH-716 | The channel locale policy carries required fields and a UI locale setting and per-message locale tag |
| B0B-UNCOVERED_ARCH-718 | Prose flooding on AI-AI channels triggers a warning and compact re-issue. |
| B0B-UNCOVERED_ARCH-720 | Agent contract defaults and contract shapes are confirmed before use. |
| B0B-UNCOVERED_BP06-6 | Persist one RoleModelProfile row per executable role per project with mode and binding and version a |
| B0B-UNCOVERED_BP06-67 | Provide per-role profile editing in AI SETTINGS with validation feedback |
| B0B-UNCOVERED_MVP_ACCEPT-178 | chat renders the user prompt plus streamed tokens incrementally and final output matches the stored |
| B0B-UNCOVERED_MVP_ACCEPT-189 | routing panel shows policy version, candidate snapshot, evidence refs with fixture provenance, and t |
| B0B-UNCOVERED_MVP_ACCEPT-199 | outage fixture asserts provider health transitions. |
| B0B-UNCOVERED_UI_DELTA-14 | configures each role model through a per-role RoleModelProfile map with no fixed default_manager fie |
| B0B-UNCOVERED_UI_DELTA-15 | configures each role model through a per-role RoleModelProfile map with no fixed default_manager or |
| HD-APP-ID | product identifier com.agentsi.app on installer, app data, OS registration |
| LIVE0-02 | a 404 fetch failure shows honest not-found or server-down wording, never the contract-version error |
| LIVE0-03 | a failed fetch retries under a backoff policy, no retry storm |
| LIVE0-05 | the first-run wizard renders its setup steps |
| LIVE0-08 | UI writes carry the session token from the first call (no missing-token 403) |
| LIVE0B-01 | after Add Project the new project appears in the Projects list without a full page reload |
| LIVE0B-04 | every page renders with its title and the console styling, never raw unstyled HTML |
| LIVE0B-05 | the Chat page mounts a message box that starts a task |
| M-D-D5 | frontend toolchain pinned; zero-finding dep baseline per build |
| M-P3-92 | telemetry dark plus light themes; accessible charts; visual standard |
| M-P4-139 | copyright line EN plus UK in About and installer metadata |
| M-P4-159 | context checkpoints at 70, compacts at 85; card shows window plus source |
| M-R-BRAND | first start migrates old local data plus credentials; old copies kept |
| M-R-UX-1 | one top bar; pairing as top strip, never overlay chrome |
| M-R-UX-10 | plain verb first; mirrored uk plus en keys with CI parity |
| M-R-UX-12 | chat draft chip plus spinner plus timestamp; offline queue dot |
| M-R-UX-2 | one H2 plus explainer; jargon carries a Why chip |
| M-R-UX-3 | lists for runnable items, cards for explainers; labeled failure chips |
| M-R-UX-4 | one primary verb; destructive actions secondary with confirm plus undo |
| M-R-UX-6 | single-purpose forms; bounded submit with timeout plus cancel |
| M-R-UX-7 | status chips show state plus reason plus one action |
| M-R-UX-8 | empty plus loading plus error states with next steps and causes |
| M-R-UX-9 | toasts for background events only; blocking errors inline |
| MH-5 | step mode executes one plan→action→observation turn per user advance, showing the exact model input ('what the model saw') and the observation before the next step. |
| MH-6 | every executed turn renders its plan→action→observation triple from stored records (plan ref, tool call ref, result ref) with the per-task turn-budget counter visible in the UI. |
| R-316 | edited value survives a late status load |
| R-317 | live agents panel: who, where, model, tokens |
| R-318 | compact self-scrolling inspector panel |
| R-319 | friendly self-explaining UI; newcomer knows where to start |
| R-334 | Ukrainian and English, visible switch in top bar and Settings, persisted |
| R-341-UI | benchmark settings tab: path -> scan -> level -> run with duration and PC-load warnings, results per model shown (over the K05 routes; HD 20:0x owner order) |
| R-342 | exact licence string everywhere user-visible |
| R-348 | Runs vs code tests vs local tests explained |
| R-362 | every visible string in both languages incl. errors, empty states, onboarding, telemetry; locale formats; OS-language first run |
| R-372 | Agent SI on every surface; LICENSE (MIT) shown by the installer; third-party notices (K10 ships them) |

## K08: The watcher, automations and context (28)

| Row | Requirement |
|---|---|
| 174 | covers two rows: global plus per-project pause; runs recorded under governance |
| 181 | outage means one clear stop-and-report signal |
| 186 | default watcher preset seeded on a fresh project |
| 249 | named apps card plus closing-prompt test |
| B0B-SDK-94 | supports immediate and after-turn cancellation with immediate default. |
| B0B-SDK-95 | immediate cancellation stops at once and marks the run complete. |
| B0B-SDK-96 | leaves the turn uncompleted on immediate cancellation. |
| B0B-SDK-99 | after-turn cancellation finishes the current turn before stopping. |
| B0B-UNCOVERED_ARCH-641 | Finalization consumes VerificationRecord outputs traced to the verification sections. |
| B0B-UNCOVERED_ARCH-642 | Finalization consumes AuditRecord outputs owned by the audit sections. |
| M-P2-68 | helper-provider outage: telemetry; small audits on free models |
| M-P3-112 | no script builder; built-in or import only |
| M-P3-94 | missed timed-rule fires: skip or once-run per catch-up; survive restart |
| M-P4-160 | context save-restore benchmarked vs Keeper; sourced or UNKNOWN |
| R-320 | disk check plus own-temp cleanup, journaled, own folders only |
| R-321 | workspace escape detected from facts; alert plus block |
| R-322 | watcher untouchable; supervised restart; attempts journaled |
| R-323 | one-click Stop all, user-only or expiring grant, journaled |
| R-324 | watcher alerts, never stops agents itself |
| R-325 | watcher on local AI picks script plus parameters per rule |
| R-326 | stop on a running hierarchy stops everything |
| R-327 | run temp files removed by the standard cleanup script |
| R-335 | timers, auto-launchers, metric-triggered actions, recorded and pausable |
| R-336 | Watcher tab + settings; local AI default, cloud fallback, off |
| R-337 | per-service in-use / last-used / agent usage; Docker leak scan; protected refused |
| R-363 | automation templates, no-code rule builder, launchers resume after restart/crash/outage, metric triggers, context register |
| R-364 | Watcher rule cards, presets, own area, model local / API / OFF, standard set with 20-min hang default |
| R-366 | declared services: check types, UP/DOWN/DEGRADED, observe + notify, usage from metadata, outage linkage |

## K09: Knowledge bases (9)

| Row | Requirement |
|---|---|
| 144 | web fallbacks counted per role |
| 145 | index-first reads; retrieval cost recorded |
| 146a | universal connector plus a documented foreign-shape adapter |
| 146c | format spec plus builder guide plus templates plus validator CLI |
| 209 | keeper guide for new models and prices, validated by tests |
| B0B-UNCOVERED_BP05-43 | Knowledge retrieval MUST stay DATA_ONLY and large handoffs MUST use ArtifactRef by ref and environme |
| LIVE0-06 | stale KB copies refresh with versions through an update or proposal-fetch route |
| M-P2-74 | KB reads behind manifest index; section logging; no whole-KB reads |
| R-361 | KB use optional, read-only, per project and role switch; hits, misses, web fallbacks and savings from records |

## K10: The installer, proofs and acceptance (53)

| Row | Requirement |
|---|---|
| 165 | exe produced by the script; hash plus smoke recorded |
| 166 | human-like end-to-end run with screenshots as release evidence |
| 167 | installed-app check on a clean profile |
| B0B-UNCOVERED_ARCH-512 | Abort streams cleanly on request; complete the turn gracefully after abort |
| B0B-UNCOVERED_MVP_ACCEPT-129 | README holds setup instructions plus a demo and fixture command index and adds no install content be |
| B0B-UNCOVERED_MVP_ACCEPT-130 | MVP acceptance verification checks README plus setup instructions alongside demos and fixtures. |
| B0B-UNCOVERED_MVP_ACCEPT-131 | README at checkout root documents prerequisites, setup steps, demo commands, fixture commands, task |
| B0B-UNCOVERED_MVP_ACCEPT-132 | acceptance map links each checklist item to its design section and evidence. |
| B0B-UNCOVERED_MVP_ACCEPT-151 | clean checkout boot follows documented steps, uses versioned dependencies, and yields identical work |
| B0B-UNCOVERED_MVP_ACCEPT-152 | reproducible startup is verified alongside demos, fixtures, and UI checks. |
| B0B-UNCOVERED_MVP_ACCEPT-153 | startup sequence (checkout, configure from environment example, offline install from lockfiles, laun |
| B0B-UNCOVERED_MVP_ACCEPT-154 | clean-state restart twice yields identical working startup. |
| B0B-UNCOVERED_MVP_ACCEPT-158 | project analytics view aggregates project-level task and audit counts deterministically. |
| B0B-UNCOVERED_MVP_ACCEPT-160 | model and provider analytics shows per-model and per-provider calls plus tokens plus cost or UNAVAIL |
| B0B-UNCOVERED_MVP_ACCEPT-161 | analytics values read only from authoritative TelemetryEvent and MetricRecord stores, never from cha |
| B0B-UNCOVERED_MVP_ACCEPT-172 | fixture capability rows are labelled TEST FIXTURES with provenance and are never measured evidence. |
| B0B-UNCOVERED_MVP_ACCEPT-173 | MVP fixture pack ships under checkout and is not measured evidence. |
| B0B-UNCOVERED_MVP_ACCEPT-200 | report export contains dataset rows per demo and fixture with referenced artifacts, versions, provid |
| B0B-UNCOVERED_MVP_ACCEPT-209 | MVP verdict is binary ACCEPTED or NOT_ACCEPTED with explicit blockers. |
| B0B-UNCOVERED_MVP_ACCEPT-210 | MVP_ACCEPTED equals ACCEPTED iff all acceptance items hold. |
| B0B-UNCOVERED_MVP_ACCEPT-211 | MVP acceptance requires README plus secret-free environment example plus twice-identical reproducibl |
| B0B-UNCOVERED_MVP_ACCEPT-212 | MVP shortfall yields NOT_ACCEPTED with listed blockers. |
| B0B-UNCOVERED_MVP_ACCEPT-214 | host blockers name missing permissions, auditor provider, and second provider. |
| B0B-UNCOVERED_MVP_ACCEPT-215 | MVP is not attainable on a host until local permission, auditor provider, and a second real provider |
| B0B-UNCOVERED_MVP_ACCEPT-217 | TEST FIXTURE rows prove wiring only and are never presented as measured evidence. |
| B0B-UNCOVERED_MVP_ACCEPT-225 | local demo needs a permission-gated local runtime plus capability evidence for the fixture class. |
| B0B-UNCOVERED_MVP_ACCEPT-227 | split demo includes real cloud verification over the local draft output with draft-hash binding befo |
| B0B-UNCOVERED_MVP_ACCEPT-229 | unavailable local legs use labelled localhost mock doubles as TEST FIXTURES. |
| B0B-UNCOVERED_MVP_ACCEPT-231 | provider set needs two reachable providers with cross-provider routing; design-level doubles alone d |
| B0B-UNCOVERED_MVP_ACCEPT-233 | unsatisfied provider set is recorded as a blocker. |
| B0B-UNCOVERED_MVP_ACCEPT-235 | local stand-ins are localhost mock endpoints with TEST FIXTURE provenance, never measured evidence. |
| B0B-UNCOVERED_MVP_ACCEPT-242 | offline install contacts no package registry. |
| B0B-UNCOVERED_MVP_ACCEPT-243 | install with an absent wheel aborts and records startup FAILED with no silent substitution. |
| B0B-UNCOVERED_MVP_ACCEPT-246 | frontend install with a missing cached tarball aborts and records startup FAILED. |
| B0B-UNCOVERED_MVP_ACCEPT-248 | startup log records backend plus frontend locked versions. |
| B0B-UNCOVERED_MVP_ACCEPT-249 | clean-checkout restart twice shows identical versions and identical working startup. |
| B0B-UNCOVERED_MVP_ACCEPT-250 | startup log records the provider set including mock doubles and absent real providers. |
| B0B-UNCOVERED_MVP_ACCEPT-251 | absent second real provider is recorded as a blocker. |
| HC-4 | open-source licence check (owner decision) |
| LIVE0-01 | frontend install from cached tarballs proves the declared @types set |
| LIVE0-04 | the product start path supplies the data dir, no harness settings |
| M-P3-89 | portable folder start script; identical behaviour |
| M-P4-134 | first start migrates settings plus credentials; originals kept |
| M-P4-138 | first start migrates settings plus keys; originals kept |
| M-P4-143 | competitor findings with source plus quote; ranked; rules plus packages |
| M-P4-153 | first-time person reaches finished first task by clicks |
| M-P4-162 | final acceptance covers Docker, declared services, PowerShell |
| M-P4-166 | every package combines best plus KB plus benchmark plus Watcher on DEFAULT |
| M-R-COMPET | competitive audit flow by flow; fetched source plus snippet per claim |
| R-328 | demo project brought to green inside the acceptance drive |
| R-343 | fresh install holds no test data |
| R-345 | no fullscreen flash on start, no console flash on close |
| R-351 | acceptance on the tech-handbook copy, all functions, n8n excluded (git + code-audit suites only), final evidence table [n8n excluded = PARKED-OWNER, owner 16:0x] |

## K11: Follow-up (6)

**Not part of this release.** The plan set these rows as follow-up work for after the release. Its table marks them DEFAULT too, but this release has no macOS build, and these rows were not checked. Do not read them as shipped.

| Row | Requirement |
|---|---|
| R-329 | scheduled follow-up after release acceptance |
| R-330 | scheduled follow-up after release acceptance |
| R-331 | scheduled follow-up after release acceptance |
| R-352 | large parallel builds inside the app |
| R-353 | partner research + one small partner integration |
| R-354 | macOS build, Keychain behind the secret-store protocol |

## K12: Presentation and demo (3)

| Row | Requirement |
|---|---|
| HC-2 | CONTRIBUTIONS kept current per accepted package |
| HC-3 | public repo + secret/private scan before final submission |
| R-350 | idea text, presentation, video demo, public-text rules |

## K13: The run core: contracts and state machines (23)

| Row | Requirement |
|---|---|
| B0B-BP08-32 | forbids trace export for secrets-bearing runs unless explicitly authorized. |
| B0B-BP08-61 | keeps secrets-bearing traces local-only with redaction and no external export. |
| B0B-SDK-18 | disables SDK tracing by default unless policy enables it. |
| B0B-SDK-90 | never attempts hosted trace export without a configured key. |
| B0B-UNCOVERED_ARCH-125 | ExecutionRun carries a stored status field and derivation stays consistent with attempt history plus |
| B0B-UNCOVERED_ARCH-169 | Same-named registrations from different runtimes stay distinct in registries |
| B0B-UNCOVERED_ARCH-329 | Reject unknown event_type values; new event types need an explicit vocabulary decision; never invent |
| B0B-UNCOVERED_ARCH-404 | Default SDK tracing to disabled or local-processor-only unless 0C explicitly decides otherwise |
| B0B-UNCOVERED_BP04-36 | TelemetryEvent envelopes and MetricRecords are append-only; corrections arrive as new records |
| B0B-UNCOVERED_BP04-43 | Appending an event with an existing event_id returns the stored record without creating a duplicate |
| B0B-UNCOVERED_BP04-53 | New event types arrive only as a new vocabulary version; silent extension of the active version is r |
| B0B-UNCOVERED_BP04-54 | Envelopes referencing an unknown event type are rejected before EventStore append with a recorded re |
| B0B-UNCOVERED_BP05-2 | registries MUST expose registration plus lookup plus health views for indexed entries; health views |
| B0B-UNCOVERED_BP05-3 | registries MUST NOT own execution or routing decisions or secret values; execution belongs to runs a |
| B0B-UNCOVERED_BP05-54 | Bulk inline transfer MUST be re-issued by ArtifactRef at handoff audit instead of passing inline. |
| B0B-UNCOVERED_BP06-13 | Resolve concurrent configuration edits by version ordering and never apply a silent rewrite |
| B0B-UNCOVERED_MVP_ACCEPT-6 | DEMO-1 LOCAL runs one ExecutionRun with an INITIAL attempt on the local OpenAI-compatible endpoint; |
| M-D-D2 | security records as bounded additive deltas; versioned migrations |
| M-D-D33 | repositories compose under one unit of work; atomic multi-record writes |
| M-D-D4 | auditor PASS only on full routed criteria; evidence refs persist |
| M-D-D40 | local compute via precheck plus reserve plus reconcile with leases |
| M-D-D6 | project plus decision records atomic; unattributed actor anonymous |
| M-D-D7 | turn risk from stored contract; structured refusal with risk plus ids |
