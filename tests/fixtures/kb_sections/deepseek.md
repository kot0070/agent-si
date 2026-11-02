# DeepSeek — KB (retrieved 2026-10-11)

## deepseek-v4-pro

- Model ID: deepseek-v4-pro (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Context window: 1000000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Max output: 384000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Modalities: ["text"] (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Tool calling: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Structured output: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Reasoning: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://api-docs.deepseek.com/guides/thinking_mode, retrieved 2026-10-11).
- Release date: 2026-08-13 (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Status: live (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Price input per 1M tokens: 1.32 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 3.96 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price currency: USD (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price date: 2026-10-11 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a DeepSeek-V4-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on GA agent scores: Terminal-Bench 2.1 87.9, Toolathlon-Verified 74.1, Thinking effort low/high/max, default high, Supports tools, JSON, Responses API, Anthropic API.
- Weaknesses (analysis): watch out for No vision input, Peak price 2x off-peak; concurrency limit 500, Knowledge cutoff not disclosed.
- Best for (analysis): suited to agent loops, code generation and review, hard reasoning and planning.
- Avoid for (analysis): less suited to cutoff-sensitive factual QA, vision input tasks, simple bulk jobs where flash is cheaper.
- Task fit (analysis): agent-loop: best; code-gen: best; code-review: best; long-doc: good; math-reasoning: best; planning: best; routing: ok; short-chat: good.
- Role notes (analysis): auditor role: Use max effort for audit-grade review; preserve reasoning_content trace.; director role: Strongest DeepSeek planner; use for hard decomposition.; manager role: Good multi-step delegator; schedule off-peak to halve cost.; worker role: Best quality code-gen worker when cost is secondary..
- Speed class (analysis): standard.
Analysis basis: https://api-docs.deepseek.com/quick_start/pricing, https://api-docs.deepseek.com/updates, https://api-docs.deepseek.com/guides/thinking_mode, https://api-docs.deepseek.com/guides/vision (retrieved 2026-10-11).

## deepseek-flash

- Model ID: deepseek-flash (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Context window: 1000000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Max output: 384000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://api-docs.deepseek.com/guides/vision, retrieved 2026-10-11).
- Tool calling: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Structured output: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Reasoning: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://api-docs.deepseek.com/guides/vision, retrieved 2026-10-11).
- Release date: 2026-09-10 (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Status: live (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Price input per 1M tokens: 0.3 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 1.2 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price currency: USD (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price date: 2026-10-11 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a DeepSeek-V4.1-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Native multimodal vision (JPEG/PNG/GIF/WebP, 600 images max), Peak input $0.30/1M, off-peak half; concurrency 2500, Benchmarks: GPQA Diamond 90.9, Terminal-Bench 2.1 90.6.
- Weaknesses (analysis): watch out for Weaker than pro on hard agent benchmarks, Knowledge cutoff not disclosed, Thinking mode disables temperature penalties (fixed behavior).
- Best for (analysis): suited to cheap bulk chat and coding, vision QA and chart reading, high-throughput agent loops.
- Avoid for (analysis): less suited to max-quality deep reasoning (use v4-pro), cutoff-sensitive QA, tasks needing disclosed cutoff.
- Task fit (analysis): agent-loop: good; bulk-summary: best; code-gen: good; code-review: good; long-doc: good; routing: best; short-chat: best; vision: best.
- Role notes (analysis): auditor role: Cheap re-check pass; vision claims need second source.; director role: Default router choice for cost-aware delegation.; manager role: Good fan-out worker; batch off-peak.; worker role: Default worker for code, vision, bulk summary..
- Speed class (analysis): fast.
Analysis basis: https://api-docs.deepseek.com/quick_start/pricing, https://api-docs.deepseek.com/updates, https://api-docs.deepseek.com/guides/thinking_mode, https://api-docs.deepseek.com/guides/vision (retrieved 2026-10-11).

## deepseek-v4-flash

- Model ID: deepseek-v4-flash (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Context window: 1000000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Max output: 384000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Modalities: UNKNOWN (checked https://api-docs.deepseek.com/guides/vision, retrieved 2026-10-11).
- Tool calling: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Structured output: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Reasoning: true (https://api-docs.deepseek.com/guides/thinking_mode, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Release date: 2026-04-24 (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Status: live-alias (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Price input per 1M tokens: 0.3 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 1.2 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price currency: USD (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price date: 2026-10-11 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a DeepSeek-V4-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Still accepted; served by V4.1-Flash and billed at Flash price, Same 1M context and 384K output envelope.
- Weaknesses (analysis): watch out for Backend retired; compatibility routing may end, Vision-exp variant behavior merged into flash.
- Best for (analysis): suited to legacy code still calling deepseek-v4-flash, cheap bulk chat during migration.
- Avoid for (analysis): less suited to new integrations (use deepseek-flash), expecting original V4-Flash weights, cutoff-sensitive QA.
- Task fit (analysis): agent-loop: ok; bulk-summary: good; code-gen: good; routing: ok; short-chat: best.
- Role notes (analysis): auditor role: Treat as flash alias; verify backend version in responses.; director role: Do not assign; migrate callers to deepseek-flash.; manager role: Temporary alias only.; worker role: Works as flash; prefer canonical id..
- Speed class (analysis): fast.
Analysis basis: https://api-docs.deepseek.com/quick_start/pricing, https://api-docs.deepseek.com/updates, https://api-docs.deepseek.com/guides/thinking_mode (retrieved 2026-10-11).

## deepseek-v4-flash-vision-exp

- Model ID: deepseek-v4-flash-vision-exp (https://api-docs.deepseek.com/guides/vision, retrieved 2026-10-11).
- Context window: 1000000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Max output: 384000 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://api-docs.deepseek.com/guides/vision, retrieved 2026-10-11).
- Tool calling: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Structured output: true (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Reasoning: true (https://api-docs.deepseek.com/guides/thinking_mode, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Release date: 2026-08-21 (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Status: live-alias (https://api-docs.deepseek.com/updates, retrieved 2026-10-11).
- Price input per 1M tokens: 0.3 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 1.2 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price currency: USD (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).
- Price date: 2026-10-11 (https://api-docs.deepseek.com/quick_start/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a DeepSeek-V4-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Still accepted; served by V4.1-Flash at Flash price, Vision capability preserved via flash backend.
- Weaknesses (analysis): watch out for Experimental backend retired; routing temporary, No separate benchmarks for the alias itself.
- Best for (analysis): suited to legacy vision code calling the exp name, image QA during migration.
- Avoid for (analysis): less suited to new integrations (use deepseek-flash), general text-only bulk (use canonical flash id), cutoff-sensitive QA.
- Task fit (analysis): agent-loop: ok; bulk-summary: good; routing: ok; short-chat: best; vision: best.
- Role notes (analysis): auditor role: Vision claims need second source; alias may vanish.; director role: Do not assign; migrate to deepseek-flash.; manager role: Temporary alias only.; worker role: Works as flash vision; prefer canonical id..
- Speed class (analysis): fast.
Analysis basis: https://api-docs.deepseek.com/quick_start/pricing, https://api-docs.deepseek.com/updates, https://api-docs.deepseek.com/guides/vision, https://api-docs.deepseek.com/guides/thinking_mode (retrieved 2026-10-11).

## Sources & retrieval dates

- https://api-docs.deepseek.com/quick_start/pricing — 2026-10-11
- https://api-docs.deepseek.com/guides/thinking_mode — 2026-10-11
- https://api-docs.deepseek.com/updates — 2026-10-11
- https://api-docs.deepseek.com/guides/vision — 2026-10-11
