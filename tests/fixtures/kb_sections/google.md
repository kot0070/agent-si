# Google — KB (retrieved 2026-10-11)

## gemini-3.8-flash

- Model ID: gemini-3.8-flash (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Release date: 2026-09-02 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, retrieved 2026-10-11).
- Price input per 1M tokens: 0.75 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 3.75 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: USD (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-3-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on flagship Flash intelligence; thinking (low/medium/high); function calling + structured outputs; search/Maps grounding; code execution; 1M context.
- Weaknesses (analysis): watch out for promo pricing expires 2026-12-31 (doubles 2027-01-01); 65k output cap; no native image output.
- Best for (analysis): suited to agent loops, long-horizon software engineering, enterprise workflows, long-context reasoning.
- Avoid for (analysis): less suited to real-time voice (use Live models), image generation (use Nano Banana), sub-second latency bulk work.
- Task fit (analysis): agent-loop: best; code-gen: best; code-review: best; long-doc: best; math-reasoning: best; planning: best; routing: best; short-chat: good; vision: good.
- Role notes (analysis): auditor role: good for cited long-doc audit with search grounding; director role: best default for planning + routing; manager role: best for decomposing multi-step work; worker role: best for code-gen and agent-loop execution.
- Speed class (analysis): fast.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-3.6-flash

- Model ID: gemini-3.6-flash (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Release date: 2026-07-21 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash, retrieved 2026-10-11).
- Price input per 1M tokens: 0.75 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 3.75 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: USD (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-3-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on previous-gen Flash balancing speed and multimodal ability; grounding + caching support.
- Weaknesses (analysis): watch out for superseded by 3.8 Flash; promo pricing expires end 2026.
- Best for (analysis): suited to general agentic tasks, everyday multimodal work, chat + tool use.
- Avoid for (analysis): less suited to bleeding-edge reasoning max (use 3.1 Pro preview or 3.8 Flash).
- Task fit (analysis): agent-loop: good; code-gen: good; long-doc: good; planning: good; routing: good; short-chat: best; vision: good.
- Role notes (analysis): auditor role: good for review with grounding; director role: good planner fallback; manager role: good task splitter; worker role: good executor.
- Speed class (analysis): fast.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-3.5-flash-lite

- Model ID: gemini-3.5-flash-lite (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Release date: 2026-07-21 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, retrieved 2026-10-11).
- Price input per 1M tokens: 0.3 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 2.5 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: USD (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-3-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on cheapest current chat Flash; grounding support; batch/flex discounts.
- Weaknesses (analysis): watch out for weaker reasoning vs Flash/Pro; no context caching on standard tier per pricing page.
- Best for (analysis): suited to high-volume agentic tasks, translation, simple data processing, bulk summary.
- Avoid for (analysis): less suited to deep reasoning, large code refactors.
- Task fit (analysis): agent-loop: ok; bulk-summary: best; routing: best; short-chat: best; translation-uk-en: good.
- Role notes (analysis): auditor role: ok for cheap first-pass triage; director role: good for routing/bulk dispatch; manager role: good for fan-out; worker role: best for bulk-summary and short-chat.
- Speed class (analysis): fastest.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-3.1-flash-lite

- Model ID: gemini-3.1-flash-lite (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Release date: 2026-05-07 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite, retrieved 2026-10-11).
- Price input per 1M tokens: 0.25 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 1.5 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: USD (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-3-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on lowest text input price of Gemini chat line; audio input supported at higher rate.
- Weaknesses (analysis): watch out for lowest capability tier; audio input costs 2x text rate.
- Best for (analysis): suited to high-frequency lightweight tasks, translation, cheap bulk processing.
- Avoid for (analysis): less suited to frontier reasoning, heavy agentic coding.
- Task fit (analysis): bulk-summary: best; routing: best; short-chat: best; translation-uk-en: good.
- Role notes (analysis): auditor role: avoid as sole auditor; director role: good cheap router; manager role: good for splitting bulk work; worker role: best for cheap fast drafts.
- Speed class (analysis): fastest.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-3.1-pro-preview

- Model ID: gemini-3.1-pro-preview (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Release date: 2026-02-19 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: preview (https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview, retrieved 2026-10-11).
- Price input per 1M tokens: 2.0 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 12.0 (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: USD (https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-3-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on 3rd-gen Pro: multimodal understanding, agentic + vibe-coding focus; tiered long-prompt pricing.
- Weaknesses (analysis): watch out for preview status; no free tier; price jumps past 200k-token prompts ($4/$18).
- Best for (analysis): suited to complex problem solving, multimodal understanding, vibe-coding, agentic planning.
- Avoid for (analysis): less suited to cheap bulk work, latency-sensitive simple chat.
- Task fit (analysis): agent-loop: good; code-gen: best; long-doc: best; math-reasoning: best; planning: best; vision: good.
- Role notes (analysis): auditor role: best for deep audit; director role: best for hard planning; manager role: best for complex decomposition; worker role: best for hard code-gen.
- Speed class (analysis): slow.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-2.5-pro

- Model ID: gemini-2.5-pro (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Knowledge cutoff: 2025-01-01 (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Release date: 2025-06-17 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-2.5-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on state-of-the-art 2.5 thinking model; search grounding; file search; URL context.
- Weaknesses (analysis): watch out for access restricted to past users; capacity reserved for legacy workflows; price not re-verified this session.
- Best for (analysis): suited to complex code/math/STEM reasoning, large codebase and dataset analysis (legacy continuity).
- Avoid for (analysis): less suited to new projects (Google advises 3.5 Flash-Lite or 3.8 Flash); real-time voice.
- Task fit (analysis): code-gen: best; code-review: best; long-doc: best; math-reasoning: best; planning: best.
- Role notes (analysis): auditor role: good legacy auditor; director role: good legacy planner; manager role: good legacy decomposer; worker role: good legacy coder.
- Speed class (analysis): slow.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-2.5-flash

- Model ID: gemini-2.5-flash (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Context window: 1048576 (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Max output: 65536 (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio"] (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Tool calling: true (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Structured output: true (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Reasoning: true (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Knowledge cutoff: 2025-01-01 (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Release date: 2025-06-17 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-2.5-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on best 2.5 price-performance; thinking support; agentic use cases.
- Weaknesses (analysis): watch out for access restricted to past users; superseded by Gemini 3 line.
- Best for (analysis): suited to price-performance legacy workloads, large-scale processing, low-latency high-volume thinking tasks.
- Avoid for (analysis): less suited to new projects (use 3.5 Flash-Lite or 3.8 Flash per Google note).
- Task fit (analysis): agent-loop: good; bulk-summary: good; routing: good; short-chat: best.
- Role notes (analysis): auditor role: ok legacy triage; director role: good legacy router; manager role: good legacy fan-out; worker role: good legacy executor.
- Speed class (analysis): fast.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## gemini-embedding-001

- Model ID: gemini-embedding-001 (https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Context window: 2048 (https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Modalities: ["text"] (https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Tool calling: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Release date: 2025-07-14 (https://ai.google.dev/gemini-api/docs/deprecations, retrieved 2026-10-11).
- Status: stable (https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://ai.google.dev/gemini-api/docs/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gemini-embedding-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on high-dimensional vectors; RAG-ready; successor gemini-embedding-2 available.
- Weaknesses (analysis): watch out for shutdown scheduled 2028-05-14; migrate to gemini-embedding-2.
- Best for (analysis): suited to semantic search, text classification, RAG embeddings.
- Avoid for (analysis): less suited to chat, code-gen, reasoning (not a generative model).
- Task fit (analysis): embeddings: best.
- Role notes (analysis): auditor role: good for retrieval-backed audit; director role: ok for memory retrieval; manager role: ok for context assembly; worker role: best for RAG lookup.
- Speed class (analysis): fastest.
Analysis basis: https://ai.google.dev/gemini-api/docs/models, https://ai.google.dev/gemini-api/docs/pricing, https://ai.google.dev/gemini-api/docs/deprecations, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview (retrieved 2026-10-11).

## Sources & retrieval dates

- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash — 2026-10-11
- https://ai.google.dev/gemini-api/docs/deprecations — 2026-10-11
- https://ai.google.dev/gemini-api/docs/pricing — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash — 2026-10-11
- https://ai.google.dev/gemini-api/docs/models/gemini-embedding-001 — 2026-10-11
