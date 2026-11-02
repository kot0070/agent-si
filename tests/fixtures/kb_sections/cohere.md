# Cohere — KB (retrieved 2026-10-11)

## command-a-plus-05-2026

- Model ID: command-a-plus-05-2026 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 128000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: 64000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://docs.cohere.com/docs/tool-use, retrieved 2026-10-11).
- Structured output: true (https://docs.cohere.com/docs/structured-outputs, retrieved 2026-10-11).
- Reasoning: true (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: live (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Command-A-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on First Cohere MoE combining vision, agents, reasoning, translation, Fits 1xB200 or 2xH100; higher throughput than Reasoning variant, 128K context with 64K output.
- Weaknesses (analysis): watch out for Per-token price not published on pricing page (Model Vault instance pricing), Knowledge cutoff undisclosed, Newer model with less community benchmark coverage.
- Best for (analysis): suited to agentic tool-use loops, RAG over long docs, multilingual enterprise chat.
- Avoid for (analysis): less suited to embeddings or rerank (use Embed/Rerank endpoints), speech transcription, simple bulk chat where R7B is cheaper.
- Task fit (analysis): agent-loop: best; code-review: good; long-doc: best; planning: best; routing: good; short-chat: good; vision: good.
- Role notes (analysis): auditor role: Strong audit reviewer; verify citations via RAG sources.; director role: Flagship for complex delegation; watch unknown per-token cost.; manager role: Best multi-step agent manager in Cohere lineup.; worker role: Use for hard reasoning steps; R7B for cheap steps..
- Speed class (analysis): standard.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/tool-use, https://docs.cohere.com/docs/structured-outputs, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## command-a-03-2025

- Model ID: command-a-03-2025 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 256000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: 8000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://docs.cohere.com/docs/command-a, retrieved 2026-10-11).
- Structured output: true (https://docs.cohere.com/docs/structured-outputs, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.cohere.com/docs/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: live (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Command-A-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on 111B params, 256K context, runs on 2 GPUs, 150 percent higher throughput than Command R+ 08-2024, Strong tool-use avoiding unnecessary calls.
- Weaknesses (analysis): watch out for 8K max output limits long generations, Per-token price not published (instance pricing), Cutoff undisclosed.
- Best for (analysis): suited to tool use and agents, RAG pipelines, multilingual chat (23 languages).
- Avoid for (analysis): less suited to vision input (use A+ or A-Vision), embeddings or rerank tasks, speech transcription.
- Task fit (analysis): agent-loop: best; bulk-summary: good; code-gen: good; long-doc: best; planning: good; routing: good; short-chat: good.
- Role notes (analysis): auditor role: Solid grounded QA reviewer via RAG citations.; director role: Workhorse planner for RAG/agent fleets.; manager role: Good delegation manager; 2-GPU deployable.; worker role: Strong general worker; cap output expectations at 8K..
- Speed class (analysis): standard.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/command-a, https://docs.cohere.com/docs/structured-outputs, https://docs.cohere.com/docs/tool-use, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## command-r7b-12-2024

- Model ID: command-r7b-12-2024 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 128000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: 4000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Structured output: true (https://docs.cohere.com/docs/structured-outputs, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.cohere.com/docs/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: live (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Command-R-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Small fast model for RAG, tool use, agents, Most cost-effective Command tier per third-party pricing surveys, 128K context.
- Weaknesses (analysis): watch out for 4K output cap, Weaker on nuanced reasoning, Exact per-token price not on official page.
- Best for (analysis): suited to high-volume simple QA and classification, cheap RAG and tool-use steps, bulk routing and triage.
- Avoid for (analysis): less suited to long-doc synthesis over 128K, vision or speech tasks, max-quality reasoning chains.
- Task fit (analysis): agent-loop: good; bulk-summary: good; code-gen: ok; long-doc: ok; routing: best; short-chat: best.
- Role notes (analysis): auditor role: Use for cheap first-pass checks only.; director role: Cheapest routing tier for fan-out.; manager role: Bulk triage manager.; worker role: Default cheap worker for simple steps..
- Speed class (analysis): fast.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/structured-outputs, https://docs.cohere.com/docs/tool-use, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## command-a-reasoning-08-2025

- Model ID: command-a-reasoning-08-2025 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 256000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: 32000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: true (https://docs.cohere.com/docs/command-a-reasoning, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://docs.cohere.com/docs/structured-outputs, retrieved 2026-10-11).
- Reasoning: true (https://docs.cohere.com/docs/command-a-reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: live (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Command-A-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on First Cohere reasoning model with explicit think step, 256K context with 32K output, 23-language reasoning coverage.
- Weaknesses (analysis): watch out for Slower than non-reasoning siblings, Per-token price unpublished, Cutoff undisclosed.
- Best for (analysis): suited to math and nuanced problem solving, multi-step agent reasoning (23 languages), planning with think-before-answer.
- Avoid for (analysis): less suited to vision tasks, embeddings or rerank, simple chat where cheaper models win.
- Task fit (analysis): agent-loop: best; code-review: good; long-doc: good; math-reasoning: best; planning: best; routing: ok; short-chat: ok.
- Role notes (analysis): auditor role: Best Cohere auditor for step-by-step verification.; director role: Use for hard planning nodes.; manager role: Reasoning manager for complex subgoals.; worker role: Use for math-reasoning subtasks..
- Speed class (analysis): standard.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/command-a-reasoning, https://docs.cohere.com/docs/reasoning, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## command-a-vision-07-2025

- Model ID: command-a-vision-07-2025 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 128000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: 8000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: false (https://docs.cohere.com/docs/command-a-vision, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://docs.cohere.com/docs/structured-outputs, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.cohere.com/docs/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: live (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Command-A-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on First Cohere image-input model: charts, OCR, tables, Official EN/PT/IT/FR/DE/ES support, 128K context.
- Weaknesses (analysis): watch out for 8K output cap, Language support narrower than text models, Price unpublished.
- Best for (analysis): suited to chart and diagram analysis, document QA with OCR and tables, object detection style QA.
- Avoid for (analysis): less suited to text-only bulk (cheaper models win), embeddings or speech, long 256K-doc RAG (use Command A).
- Task fit (analysis): agent-loop: good; long-doc: good; routing: ok; short-chat: good; vision: best.
- Role notes (analysis): auditor role: Verify visual claims against source images.; director role: Assign all image-bearing subtasks here.; manager role: Vision-capable manager for doc pipelines.; worker role: Default Cohere vision worker..
- Speed class (analysis): standard.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/command-a-vision, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## embed-v5.0-pro

- Model ID: embed-v5.0-pro (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 128000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: false (https://docs.cohere.com/docs/tool-use, retrieved 2026-10-11).
- Structured output: false (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.cohere.com/docs/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://docs.cohere.com/docs/how-does-cohere-pricing-work, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://docs.cohere.com/docs/how-does-cohere-pricing-work, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Embed-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on Most capable Cohere embedding model, text+images+PDFs, Flexible dims 256-2048, cosine/dot/Euclidean, 128K context.
- Weaknesses (analysis): watch out for Higher latency than fast variant, Priced per embedded tokens, not chat tokens, No generative output.
- Best for (analysis): suited to embeddings for search and RAG, classification and clustering, multimodal (text+image) retrieval.
- Avoid for (analysis): less suited to chat generation, translation (use Translate model), speech tasks.
- Task fit (analysis): embeddings: best; long-doc: good; routing: good.
- Role notes (analysis): auditor role: Use for semantic duplicate detection.; director role: Retrieval backbone for RAG fleets.; manager role: Pre-filter context before LLM calls.; worker role: Embed-first step for search subtasks..
- Speed class (analysis): standard.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/tool-use, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## rerank-v4.0-pro

- Model ID: rerank-v4.0-pro (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Context window: 32000 (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Modalities: ["text"] (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Tool calling: false (https://docs.cohere.com/docs/tool-use, retrieved 2026-10-11).
- Structured output: false (https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.cohere.com/docs/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://docs.cohere.com/docs/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://docs.cohere.com/docs/how-does-cohere-pricing-work, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://docs.cohere.com/docs/how-does-cohere-pricing-work, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://cohere.com/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a Rerank-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on SOTA quality multilingual rerank incl. semi-structured JSON, 32K context vs 4K on v3.5, Pairs with Embed for search stacks.
- Weaknesses (analysis): watch out for Priced per search, not tokens, Slower than fast variant, No generation.
- Best for (analysis): suited to reranking search results, RAG precision boost, multilingual retrieval (incl. JSON data).
- Avoid for (analysis): less suited to generation or chat, embeddings, transcription.
- Task fit (analysis): embeddings: good; long-doc: good; routing: good.
- Role notes (analysis): auditor role: Re-rank evidence before final answer.; director role: Quality gate for retrieval pipelines.; manager role: Add after bulk retrieval.; worker role: Rerank-then-answer pattern..
- Speed class (analysis): standard.
Analysis basis: https://docs.cohere.com/docs/models, https://docs.cohere.com/docs/tool-use, https://docs.cohere.com/docs/how-does-cohere-pricing-work (retrieved 2026-10-11).

## Sources & retrieval dates

- https://docs.cohere.com/docs/models — 2026-10-11
- https://docs.cohere.com/docs/tool-use — 2026-10-11
- https://docs.cohere.com/docs/structured-outputs — 2026-10-11
- https://cohere.com/pricing — 2026-10-11
- https://docs.cohere.com/docs/how-does-cohere-pricing-work — 2026-10-11
- https://docs.cohere.com/docs/command-a — 2026-10-11
- https://docs.cohere.com/docs/reasoning — 2026-10-11
- https://docs.cohere.com/docs/command-a-reasoning — 2026-10-11
- https://docs.cohere.com/docs/command-a-vision — 2026-10-11
