# Meta — KB (retrieved 2026-10-11)

## muse-spark-1.3

- Model ID: muse-spark-1.3 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Context window: 1048576 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "pdf", "audio-limited"] (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Structured output: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Reasoning: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Status: current (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 1.25 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: 4.25 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: USD (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Muse Spark-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on Latest Muse Spark; improved agentic and coding performance over 1.2, 1M-token context with no long-context premium, Parallel tool calls, streamed tool-call args, reasoning across turns, structured output, search grounding.
- Weaknesses (analysis): watch out for Audio understanding degraded in 1.3 (docs advise 1.2 or Voice Transcribe for audio), Higher price than contributor tier and many Llama self-hosted options.
- Best for (analysis): suited to Agentic coding loops, multi-step tool use, long-horizon planning, repo-scale code-gen and code-review.
- Avoid for (analysis): less suited to Single-shot cheap bulk classification where contributor-tier price matters; audio-only transcription (use Voice Transcribe); image output (use Muse Image).
- Task fit (analysis): agent-loop: best; bulk-summary: good; code-gen: best; code-review: best; long-doc: best; math-reasoning: good; planning: best; routing: good; short-chat: good; vision: good.
- Role notes (analysis): auditor role: Use for audit of code and agent traces; 1M context holds whole change sets.; director role: Default choice for planning and decomposition; strongest Muse Spark reasoning incl. max effort level.; manager role: Good for fan-out task packaging and merging subagent outputs.; worker role: Best worker for code-gen, tool loops, file edits in OpenCode/Muse Code harnesses..
- Speed class (analysis): standard.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).

## muse-spark-1.2

- Model ID: muse-spark-1.2 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Context window: 1048576 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Structured output: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Status: current (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 1.25 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: 4.25 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: USD (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Muse Spark-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on Full audio understanding (unlike degraded 1.3 audio), Same 1M context and agent primitives as 1.3, Contributor variant available for cheap prototyping.
- Weaknesses (analysis): watch out for Previous version; coding quality below 1.3 per official docs, Same standard price as 1.3 so no cost reason to prefer it except audio.
- Best for (analysis): suited to Coding agents and tool loops where 1.3 is unavailable or audio input is required.
- Avoid for (analysis): less suited to Audio transcription at scale (use Voice Transcribe); image synthesis.
- Task fit (analysis): agent-loop: best; bulk-summary: good; code-gen: best; code-review: best; long-doc: best; math-reasoning: good; planning: good; routing: good; short-chat: good; vision: good.
- Role notes (analysis): auditor role: Solid auditor fallback; full audio support helps review meeting-derived specs.; director role: Capable planner; prefer 1.3 for newest work.; manager role: Good manager for dispatch and merge.; worker role: Strong worker, esp. tasks with audio attachments..
- Speed class (analysis): standard.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).

## muse-spark-1.1

- Model ID: muse-spark-1.1 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Context window: 1048576 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio", "pdf"] (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Structured output: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Status: current (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 1.25 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: 4.25 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: USD (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Muse Spark-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on Original agentic Muse Spark with computer use and multimodal perception, Same 1M context and standard-tier data privacy (no training on data).
- Weaknesses (analysis): watch out for Oldest version; superseded on coding by 1.2 and 1.3, No contributor-tier discount variant.
- Best for (analysis): suited to Legacy continuity for teams already pinned to 1.1; general chat and tool calling.
- Avoid for (analysis): less suited to New projects (prefer 1.3); heavy audio-transcription loads.
- Task fit (analysis): agent-loop: good; bulk-summary: good; code-gen: good; code-review: good; long-doc: good; math-reasoning: ok; planning: good; routing: good; short-chat: good; vision: good.
- Role notes (analysis): auditor role: Acceptable auditor when pinned; otherwise migrate.; director role: Usable planner but superseded.; manager role: Usable manager.; worker role: Usable worker for short-chat and simple code tasks..
- Speed class (analysis): standard.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).

## muse-spark-1.3-contributor

- Model ID: muse-spark-1.3-contributor (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Context window: 1048576 (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image", "video", "audio-limited", "pdf"] (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Structured output: true (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Status: current (https://dev.meta.ai/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.1 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: 0.2 (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: USD (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Muse Spark-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Heavily discounted: $0.10/$0.20 per 1M vs $1.25/$4.25 standard, Same 1M context and Muse Spark 1.3 capabilities, Lowers barrier for scaling experiments.
- Weaknesses (analysis): watch out for Prompts/completions may train future Meta models (privacy trade), Lower rate limits (100 RPM vs 3000 standard), Max reasoning level unavailable on contributor tier.
- Best for (analysis): suited to Cheap-fast prototyping, bulk-summary, short-chat, high-volume experiments where data may train future models.
- Avoid for (analysis): less suited to Production with sensitive prompts (training-eligible tier); audio transcription; image output.
- Task fit (analysis): agent-loop: good; bulk-summary: best; code-gen: good; code-review: good; long-doc: good; math-reasoning: ok; planning: ok; routing: best; short-chat: best; vision: good.
- Role notes (analysis): auditor role: Avoid for sensitive audits (data reused for training).; director role: Avoid for confidential planning.; manager role: Good for cheap fan-out trials.; worker role: Best cheap worker for bulk-summary and short-chat experiments..
- Speed class (analysis): fast.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).
- Data-use warning (Contributor tier): Contributor tier: prompts and completions may be used by Meta to train future models (https://dev.meta.ai/docs/pricing-rate-limits).
- Попередження про дані (тариф Contributor): Тариф Contributor: запити та відповіді можуть використовуватися Meta для навчання майбутніх моделей (https://dev.meta.ai/docs/pricing-rate-limits).

## muse-glimmer-30b

- Model ID: muse-glimmer-30b (https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Context window: 131072 (https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Tool calling: UNKNOWN (checked https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Reasoning: true (https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Status: current (https://dev.meta.ai/docs/muse-glimmer, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Muse Glimmer-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Open-weight Apache 2.0; self-hosted via vLLM/SGLang/llama.cpp/ExecuTorch, Distilled from Muse Spark; step-by-step reasoning; 100+ languages, No per-token API cost; data stays on own hardware.
- Weaknesses (analysis): watch out for 30B dense class below frontier Muse Spark quality, Default 128K context far below 1M Spark window.
- Best for (analysis): suited to Local always-on agents, on-device chat, privacy-sensitive routing and short-chat, fine-tuning base.
- Avoid for (analysis): less suited to 1M-context repo-scale tasks; hosted-API-only deployments; speech synthesis.
- Task fit (analysis): agent-loop: good; bulk-summary: good; code-gen: good; code-review: ok; long-doc: ok; math-reasoning: ok; planning: ok; routing: best; short-chat: best; vision: good.
- Role notes (analysis): auditor role: Local audit without data leaving host; good for offline checks.; director role: Avoid as director (smaller than Spark).; manager role: Cheap local router/dispatcher.; worker role: Good offline worker for short-chat and simple code tasks..
- Speed class (analysis): fast.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).

## llama-4-maverick

- Model ID: llama-4-maverick (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Context window: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Tool calling: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Release date: 2025-04-05 (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Status: current (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Llama 4-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on 17B active / 400B total MoE; beats GPT-4o-class on multimodal per Meta, Open weights via llama.com and Hugging Face, Natively multimodal with early fusion (context window UNKNOWN per R1 spot-check 2026-10-11).
- Weaknesses (analysis): watch out for Requires single H100 host or distributed inference, Behemoth teacher (288B active) never released; frontier path moved to closed Muse Spark.
- Best for (analysis): suited to High-quality open-weight chat, coding, multilingual, image understanding where self-hosting on a single H100 host is acceptable.
- Avoid for (analysis): less suited to Single-H100 self-hosting (too large); cheapest bulk jobs.
- Task fit (analysis): agent-loop: good; bulk-summary: good; code-gen: best; code-review: best; long-doc: ok; math-reasoning: good; planning: good; routing: ok; short-chat: good; vision: best.
- Role notes (analysis): auditor role: Strong open auditor for code and multilingual review.; director role: Good open planner; needs hosting ops.; manager role: Good manager for merge/summarise.; worker role: Best open worker for code-gen and vision tasks..
- Speed class (analysis): standard.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).

## llama-4-scout

- Model ID: llama-4-scout (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Context window: 10000000 (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Tool calling: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Release date: 2025-04-05 (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Status: current (https://ai.meta.com/blog/llama-4-multimodal-intelligence, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11).

- Family and tier (analysis): a Llama 4-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on 17B active / 109B total MoE with 16 experts; fits single H100 with Int4, 10M-token context (pre/post-trained 256K with iRoPE length generalisation), Best-in-class image grounding per Meta.
- Weaknesses (analysis): watch out for Quality below Maverick on reasoning/coding, Very long contexts need specialised serving and verification for needles.
- Best for (analysis): suited to Long-doc retrieval, multi-document summary, vast-codebase reasoning with industry-leading 10M context; single-H100 self-hosting.
- Avoid for (analysis): less suited to Absolute frontier quality (use Maverick or Muse Spark); tiny-edge deployment.
- Task fit (analysis): agent-loop: good; bulk-summary: best; code-gen: good; code-review: good; long-doc: best; math-reasoning: ok; planning: good; routing: ok; short-chat: good; vision: best.
- Role notes (analysis): auditor role: Best open auditor for very long documents.; director role: Good planner over huge corpora.; manager role: Good for map-reduce over long inputs.; worker role: Best worker for long-doc and bulk-summary..
- Speed class (analysis): standard.
Analysis basis: https://dev.meta.ai/docs/models, https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/muse-glimmer, https://ai.meta.com/blog/llama-4-multimodal-intelligence (retrieved 2026-10-11).

## Sources & retrieval dates

- https://dev.meta.ai/docs/models — 2026-10-11
- https://dev.meta.ai/docs/pricing-rate-limits — 2026-10-11
- https://dev.meta.ai/docs/muse-glimmer — 2026-10-11
- https://ai.meta.com/blog/llama-4-multimodal-intelligence — 2026-10-11

## Added 2026-10-24 (models the connected accounts offer)

- **muse-wonder-1.0** — status preview; context 1048576; modalities ['text', 'image', 'video', 'audio', 'pdf']. Price 4.0 in / 20.0 out per 1M. Best for: Complex software engineering and long-horizon agentic work: multi-file repo changes, planning with sub-agents, parallel tool calls, computer use. (https://dev.meta.ai/docs/models, 2026-10-24)
- **muse-spark-1.2-contributor** — status current; context 1048576; modalities ['text', 'image', 'video', 'audio', 'pdf']. Price 0.1 in / 0.2 out per 1M. Best for: Cheap prototyping, bulk-summary and short-chat experiments that need full audio input (the docs recommend 1.2 for audio), where data may train future models. (https://dev.meta.ai/docs/models, 2026-10-24)
- **muse-image-1.0** — status current; context unknown; modalities ['image-in', 'image-out']. Best for: Image generation and editing from text and optional reference images; charts, tables and layouts (can run code); reference-grounded images (built-in web and image search). (https://dev.meta.ai/docs/models, 2026-10-24)
- **muse-voice-transcribe-1.0** — status current; context unknown; modalities ['audio-in']. Best for: Speech-to-text: WAV files up to 10 minutes (32 MB) or realtime streams up to 60 minutes; 25 languages with code-switching; speaker diarization; turn-level timestamps. (https://dev.meta.ai/docs/models, 2026-10-24)
- **sam-3.1** — status current; context unknown; modalities ['image-in', 'video-in', 'geometry-out']. Best for: Image and video segmentation: a box and a mask for every instance of a short noun-phrase concept, with stable object identity and tracking across video frames. (https://dev.meta.ai/docs/models, 2026-10-24)
