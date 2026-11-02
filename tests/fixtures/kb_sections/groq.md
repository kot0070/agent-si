# Groq — KB (retrieved 2026-10-11)

## openai/gpt-oss-120b

- Model ID: openai/gpt-oss-120b (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Context window: 131072 (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Max output: 65536 (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Modalities: ["text"] (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Tool calling: true (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Structured output: true (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Reasoning: true (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Status: production (https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.15 (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Price output per 1M tokens: 0.6 (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Price currency: USD (https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-120b, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-oss-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on 120B open-weight reasoning at ~500 tps, built-in browser search and code execution, 131K context, 65K max completion.
- Weaknesses (analysis): watch out for open-weight quality below frontier closed models, no native vision/speech on Groq.
- Best for (analysis): suited to agent-loop, code-gen, planning, math-reasoning at speed.
- Avoid for (analysis): less suited to contexts over 131K, native vision, speech.
- Task fit (analysis): routing: good; short-chat: good; long-doc: good; code-gen: best; code-review: good; planning: best; math-reasoning: best; agent-loop: best.
- Role notes (analysis): director role: default strong-reasoning Groq host pick; manager role: planning and orchestration; worker role: code-gen and agent execution; auditor role: re-verify chains and tool args.
- Speed class (analysis): very-fast (~500 tps).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=openai/gpt-oss-120b.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/openai/gpt-oss-120b (retrieved 2026-10-11).

## openai/gpt-oss-20b

- Model ID: openai/gpt-oss-20b (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Context window: 131072 (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Max output: 65536 (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Modalities: ["text"] (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Tool calling: true (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Structured output: true (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Reasoning: true (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Status: production (https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.075 (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Price output per 1M tokens: 0.3 (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Price currency: USD (https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-20b, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-oss-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on cheapest Groq reasoning host, ~1000 tps ideal for routing and short chat, same 131K context as 120B.
- Weaknesses (analysis): watch out for 21B-class quality, weaker deep reasoning, not for hard math or long complex plans.
- Best for (analysis): suited to routing, short-chat, bulk-summary drafts.
- Avoid for (analysis): less suited to hard math-reasoning, complex planning.
- Task fit (analysis): routing: best; short-chat: best; long-doc: ok; code-gen: good; code-review: ok; planning: ok; math-reasoning: ok; agent-loop: good; bulk-summary: best.
- Role notes (analysis): director role: cheap fast triage and routing; manager role: fan-out subtask dispatch; worker role: bulk short generations; auditor role: spot-check outputs, low trust for hard claims.
- Speed class (analysis): ultra-fast (~1000 tps).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=openai/gpt-oss-20b.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/openai/gpt-oss-20b (retrieved 2026-10-11).

## llama-3.3-70b-versatile

- Model ID: llama-3.3-70b-versatile (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Context window: 131072 (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Max output: 32768 (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Modalities: ["text"] (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Tool calling: true (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Structured output: true (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Reasoning: false (https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/llama-3.3-70b-versatile, retrieved 2026-10-11).
- Status: deprecated-enterprise-only (https://console.groq.com/docs/deprecations, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).

- Family and tier (analysis): a llama-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on proven 70B instruct quality, 280 tps production history, 131K context.
- Weaknesses (analysis): watch out for deprecated for free/developer tiers 2026-08-16, Contact Sales pricing, no public rate.
- Best for (analysis): suited to legacy production compat, general chat.
- Avoid for (analysis): less suited to new builds; use gpt-oss-120b instead.
- Task fit (analysis): routing: good; short-chat: best; long-doc: good; code-gen: good; code-review: good; planning: good; math-reasoning: ok; agent-loop: good.
- Role notes (analysis): director role: legacy only, migrate off; manager role: compat routing; worker role: general text tasks; auditor role: flag deprecated usage.
- Speed class (analysis): fast (~280 tps).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=meta-llama/Llama-3.3-70B-Instruct.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/llama-3.3-70b-versatile, https://console.groq.com/docs/deprecations (retrieved 2026-10-11).

## llama-3.1-8b-instant

- Model ID: llama-3.1-8b-instant (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Context window: 131072 (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Max output: 131072 (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Modalities: ["text"] (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Tool calling: true (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Structured output: true (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Reasoning: false (https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/llama-3.1-8b-instant, retrieved 2026-10-11).
- Status: deprecated-enterprise-only (https://console.groq.com/docs/deprecations, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).

- Family and tier (analysis): a llama-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on 560 tps fastest general chat host, 131K context both directions, mature tool-use.
- Weaknesses (analysis): watch out for 8B quality ceiling, deprecated for free/developer tiers 2026-08-16.
- Best for (analysis): suited to ultra-cheap routing, short-chat legacy.
- Avoid for (analysis): less suited to new builds; use gpt-oss-20b instead.
- Task fit (analysis): routing: best; short-chat: best; long-doc: ok; code-gen: ok; code-review: ok; planning: ok; math-reasoning: avoid; agent-loop: good; bulk-summary: best.
- Role notes (analysis): director role: legacy triage only; manager role: high-fan-out dispatch; worker role: short drafts; auditor role: low trust, verify.
- Speed class (analysis): ultra-fast (~560 tps).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=meta-llama/Llama-3.1-8B-Instant.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/llama-3.1-8b-instant, https://console.groq.com/docs/deprecations (retrieved 2026-10-11).

## qwen/qwen3.8-27b

- Model ID: qwen/qwen3.8-27b (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Context window: 131072 (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Max output: 16384 (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Modalities: ["text", "vision"] (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Tool calling: true (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Structured output: true (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Reasoning: true (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Status: preview (https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.8 (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Price output per 1M tokens: 4.0 (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Price currency: USD (https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/model/qwen/qwen3.8-27b, retrieved 2026-10-11).

- Family and tier (analysis): a qwen-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on multimodal 27B with thinking/instruct modes, tunable reasoning effort, JSON mode, 450 tps preview speed.
- Weaknesses (analysis): watch out for preview, may be discontinued at short notice, 16K max completion limits long outputs.
- Best for (analysis): suited to vision short-chat, tuned-reasoning tasks.
- Avoid for (analysis): less suited to production without fallback; long-doc generation.
- Task fit (analysis): routing: good; short-chat: best; long-doc: ok; code-gen: good; code-review: good; planning: good; math-reasoning: good; agent-loop: good; vision: best.
- Role notes (analysis): director role: eval-vision pick, keep fallback; manager role: vision routing, reasoning-effort tuning; worker role: image+text tasks, OCR assist; auditor role: verify vision grounding.
- Speed class (analysis): fast (~450 tps).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=Qwen/Qwen3.8-27B.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/qwen/qwen3.8-27b (retrieved 2026-10-11).

## whisper-large-v3-turbo

- Model ID: whisper-large-v3-turbo (https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Context window: UNKNOWN (checked https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Modalities: ["audio"] (https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Tool calling: false (https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Structured output: false (https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Reasoning: false (https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Status: production (https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://console.groq.com/docs/model/whisper-large-v3-turbo, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/models, retrieved 2026-10-11).

- Family and tier (analysis): a whisper-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on fast speech-to-text host, more languages than distil-whisper.
- Weaknesses (analysis): watch out for billed per hour ($0.04/hr), not per token, 100MB file cap.
- Best for (analysis): suited to speech transcription.
- Avoid for (analysis): less suited to all text-only routing tasks.
- Task fit (analysis): speech: best; short-chat: avoid; long-doc: avoid; code-gen: avoid.
- Role notes (analysis): director role: speech pipeline only; manager role: transcription fan-out; worker role: transcribe then hand off text; auditor role: check transcript segments.
- Speed class (analysis): fast speech throughput (400K ASH, 400 RPM).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=openai/whisper-large-v3-turbo.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/whisper-large-v3-turbo (retrieved 2026-10-11).

## openai/gpt-oss-safeguard-20b

- Model ID: openai/gpt-oss-safeguard-20b (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Context window: 131072 (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Max output: 65536 (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Modalities: ["text"] (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Tool calling: true (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Structured output: true (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Reasoning: true (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Status: preview (https://console.groq.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.075 (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Price output per 1M tokens: 0.3 (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Price currency: USD (https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-oss-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on policy-following reasoning for trust and safety, bring-your-own-policy moderation, same price as gpt-oss-20b.
- Weaknesses (analysis): watch out for preview, evaluation only, not a general chat replacement.
- Best for (analysis): suited to content moderation guardrail.
- Avoid for (analysis): less suited to general code-gen or planning.
- Task fit (analysis): routing: ok; short-chat: ok.
- Role notes (analysis): director role: moderation gate; manager role: pre/post generation filter; worker role: policy checks; auditor role: primary moderation tool.
- Speed class (analysis): ultra-fast (~1000 tps).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=openai/gpt-oss-safeguard-20b.
Analysis basis: https://console.groq.com/docs/models, https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b (retrieved 2026-10-11).

## Note

- llama-3.3-70b-versatile: availability status deprecated-enterprise-only, not a full retirement (https://console.groq.com/docs/deprecations, retrieved 2026-10-11).
- llama-3.1-8b-instant: availability status deprecated-enterprise-only, not a full retirement (https://console.groq.com/docs/deprecations, retrieved 2026-10-11).

## Sources & retrieval dates

- https://console.groq.com/docs/model/openai/gpt-oss-120b — 2026-10-11
- https://console.groq.com/docs/models — 2026-10-11
- https://console.groq.com/docs/model/openai/gpt-oss-20b — 2026-10-11
- https://console.groq.com/docs/model/llama-3.3-70b-versatile — 2026-10-11
- https://console.groq.com/docs/deprecations — 2026-10-11
- https://console.groq.com/docs/model/llama-3.1-8b-instant — 2026-10-11
- https://console.groq.com/docs/model/qwen/qwen3.8-27b — 2026-10-11
- https://console.groq.com/docs/model/whisper-large-v3-turbo — 2026-10-11
- https://console.groq.com/docs/model/openai/gpt-oss-safeguard-20b — 2026-10-11
