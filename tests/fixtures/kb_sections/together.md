# Together AI — KB (retrieved 2026-10-11)

## openai/gpt-oss-120b

- Model ID: openai/gpt-oss-120b (https://www.together.ai/models/gpt-oss-120b, retrieved 2026-10-11).
- Context window: 131072 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text"] (https://www.together.ai/models/gpt-oss-120b, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://docs.together.ai/docs/inference/chat/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/gpt-oss-120b, retrieved 2026-10-11).
- Release date: 2025-08-04 (https://www.together.ai/models/gpt-oss-120b, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.15 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 0.6 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-oss-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on cheapest strong reasoning host, MXFP4 quant, function calling + structured outputs, fine-tunable on Together.
- Weaknesses (analysis): watch out for 131K context smaller than 1M rivals, open-weight ceiling.
- Best for (analysis): suited to agent-loop, code-gen on budget.
- Avoid for (analysis): less suited to 1M-context long-doc.
- Task fit (analysis): routing: good; short-chat: good; code-gen: best; code-review: good; planning: best; math-reasoning: best; agent-loop: best.
- Role notes (analysis): director role: budget reasoning default; manager role: orchestration; worker role: code execution; auditor role: verify outputs.
- Speed class (analysis): serverless shared.
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=openai/gpt-oss-120b.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://docs.together.ai/docs/inference/chat/reasoning, https://www.together.ai/pricing, https://www.together.ai/models/gpt-oss-120b (retrieved 2026-10-11).

## zai-org/GLM-5.3

- Model ID: zai-org/GLM-5.3 (https://www.together.ai/models/glm-5-3, retrieved 2026-10-11).
- Context window: 1048575 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text"] (https://www.together.ai/models/glm-5-3, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://www.together.ai/models/glm-5-3, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/glm-5-3, retrieved 2026-10-11).
- Release date: 2026-08-13 (https://www.together.ai/models/glm-5-3, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 1.4 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 4.4 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a glm-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on 1M context flagship reasoning, function calling + structured outputs, FP4 efficient serving.
- Weaknesses (analysis): watch out for $1.40/$4.40 premium over Flash, cached input still $0.26.
- Best for (analysis): suited to long-doc, planning, agent-loop over big repos.
- Avoid for (analysis): less suited to cheap bulk summarization.
- Task fit (analysis): long-doc: best; planning: best; math-reasoning: best; agent-loop: best; code-gen: best; code-review: best; routing: ok; short-chat: good.
- Role notes (analysis): director role: long-context flagship; manager role: big-repo planning; worker role: deep reasoning execution; auditor role: cross-check long-context citations.
- Speed class (analysis): serverless shared (FP4).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=zai-org/GLM-5.3.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://www.together.ai/pricing, https://www.together.ai/models/glm-5-3 (retrieved 2026-10-11).

## zai-org/GLM-5.3-Flash

- Model ID: zai-org/GLM-5.3-Flash (https://www.together.ai/models/glm-5-3-flash, retrieved 2026-10-11).
- Context window: 1048575 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text", "vision"] (https://www.together.ai/models/glm-5-3-flash, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://www.together.ai/models/glm-5-3-flash, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/glm-5-3-flash, retrieved 2026-10-11).
- Release date: 2026-08-25 (https://www.together.ai/models/glm-5-3-flash, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.15 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 0.5 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a glm-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on 1M context at $0.15/$0.50, same tool + structured support as full 5.3, best price per long-context token.
- Weaknesses (analysis): watch out for weaker than full GLM-5.3 on hard reasoning, quality gap on frontier code tasks.
- Best for (analysis): suited to long-doc triage, bulk-summary, cheap agent loops.
- Avoid for (analysis): less suited to frontier math-reasoning finals.
- Task fit (analysis): routing: good; short-chat: good; long-doc: best; code-gen: good; planning: good; agent-loop: best; bulk-summary: best.
- Role notes (analysis): director role: cheap long-context default; manager role: triage then escalate; worker role: bulk summarization; auditor role: sample-verify summaries.
- Speed class (analysis): fast serverless (FP8).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=zai-org/GLM-5.3-Flash.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://www.together.ai/pricing, https://www.together.ai/models/glm-5-3-flash (retrieved 2026-10-11).

## moonshotai/Kimi-K3

- Model ID: moonshotai/Kimi-K3 (https://www.together.ai/models/kimi-k3, retrieved 2026-10-11).
- Context window: 1048576 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text", "vision"] (https://www.together.ai/models/kimi-k3, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://docs.together.ai/docs/inference/chat/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/kimi-k3, retrieved 2026-10-11).
- Release date: 2026-07-27 (https://www.together.ai/models/kimi-k3, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 2.7 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 13.5 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a kimi-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on 1M context vision+text reasoning, strong agentic coding lineage (Kimi K2 family), function calling + structured outputs.
- Weaknesses (analysis): watch out for most expensive pick ($2.70/$13.50), promo pricing unstable.
- Best for (analysis): suited to vision long-doc, premium agent-loop.
- Avoid for (analysis): less suited to cost-sensitive bulk work.
- Task fit (analysis): long-doc: best; vision: best; agent-loop: best; code-gen: best; planning: best; math-reasoning: good; short-chat: good; routing: ok.
- Role notes (analysis): director role: premium vision-reasoning pick; manager role: multimodal planning; worker role: vision+code execution; auditor role: verify vision grounding and cost.
- Speed class (analysis): serverless shared.
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=moonshotai/Kimi-K3.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://docs.together.ai/docs/inference/chat/reasoning, https://www.together.ai/pricing, https://www.together.ai/models/kimi-k3 (retrieved 2026-10-11).

## meta-models/Muse-Glimmer-30B

- Model ID: meta-models/Muse-Glimmer-30B (https://www.together.ai/models/muse-glimmer, retrieved 2026-10-11).
- Context window: 131072 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text", "vision"] (https://www.together.ai/models/muse-glimmer, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://www.together.ai/models/muse-glimmer, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/muse-glimmer, retrieved 2026-10-11).
- Release date: 2026-08-10 (https://www.together.ai/models/muse-glimmer, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.35 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 1.5 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a muse-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on $0.35/$1.50 efficient reasoning, function calling + structured outputs, cached input only $0.04.
- Weaknesses (analysis): watch out for 30B ceiling below 100B+ models, 131K context only.
- Best for (analysis): suited to balanced code-gen and code-review.
- Avoid for (analysis): less suited to 1M-context repos.
- Task fit (analysis): code-gen: best; code-review: best; short-chat: best; routing: good; planning: good; math-reasoning: good; agent-loop: good.
- Role notes (analysis): director role: balanced mid-tier default; manager role: code-review dispatch; worker role: implement and review; auditor role: review correctness.
- Speed class (analysis): fast serverless (FP8).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=meta-models/Muse-Glimmer-30B.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://www.together.ai/pricing, https://www.together.ai/models/muse-glimmer (retrieved 2026-10-11).

## deepseek-ai/DeepSeek-V4-Pro-0813

- Model ID: deepseek-ai/DeepSeek-V4-Pro-0813 (https://www.together.ai/models/deepseek-v4-pro-0813, retrieved 2026-10-11).
- Context window: 1048576 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text"] (https://www.together.ai/models/deepseek-v4-pro-0813, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://docs.together.ai/docs/inference/chat/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/deepseek-v4-pro-0813, retrieved 2026-10-11).
- Release date: 2026-08-12 (https://www.together.ai/models/deepseek-v4-pro-0813, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 1.32 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 3.96 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a deepseek-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on 1M context deep reasoning, NVFP4 serving, cached input $0.13, strong math/code lineage.
- Weaknesses (analysis): watch out for premium output price $3.96, new 0813 snapshot, track record short.
- Best for (analysis): suited to math-reasoning, long-doc code analysis.
- Avoid for (analysis): less suited to cheap high-volume chat.
- Task fit (analysis): math-reasoning: best; long-doc: best; code-gen: best; code-review: best; planning: best; agent-loop: best; routing: ok; short-chat: good.
- Role notes (analysis): director role: math/code flagship alternate; manager role: hard-problem routing; worker role: deep analysis; auditor role: verify proofs and code.
- Speed class (analysis): serverless shared (NVFP4).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=deepseek-ai/DeepSeek-V4-Pro-0813.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://docs.together.ai/docs/inference/chat/reasoning, https://www.together.ai/pricing, https://www.together.ai/models/deepseek-v4-pro-0813 (retrieved 2026-10-11).

## MiniMaxAI/MiniMax-M3

- Model ID: MiniMaxAI/MiniMax-M3 (https://www.together.ai/models/minimax-m3, retrieved 2026-10-11).
- Context window: 524288 (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Modalities: ["text", "vision"] (https://www.together.ai/models/minimax-m3, retrieved 2026-10-11).
- Tool calling: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Structured output: true (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Reasoning: true (https://docs.together.ai/docs/inference/chat/reasoning, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://www.together.ai/models/minimax-m3, retrieved 2026-10-11).
- Release date: 2026-05-31 (https://www.together.ai/models/minimax-m3, retrieved 2026-10-11).
- Status: active (https://docs.together.ai/docs/serverless-models, retrieved 2026-10-11).
- Price input per 1M tokens: 0.3 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price output per 1M tokens: 1.2 (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price currency: USD (https://www.together.ai/pricing, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://www.together.ai/pricing, retrieved 2026-10-11).

- Family and tier (analysis): a minimax-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on 524K vision+text at $0.30/$1.20, cached input $0.06, FP4 efficient.
- Weaknesses (analysis): watch out for narrower ecosystem than Qwen/DeepSeek, mid-tier reasoning depth.
- Best for (analysis): suited to vision bulk-summary, cheap long-doc.
- Avoid for (analysis): less suited to frontier math finals.
- Task fit (analysis): vision: best; bulk-summary: best; long-doc: best; short-chat: good; routing: good; code-gen: good; agent-loop: good.
- Role notes (analysis): director role: cheap vision-long-context pick; manager role: doc+image triage; worker role: summarize and extract; auditor role: check extraction fidelity.
- Speed class (analysis): fast serverless (FP4).
- Hosting (analysis): hosted mapping; hosts_family=true, underlying model=MiniMaxAI/MiniMax-M3.
Analysis basis: https://docs.together.ai/docs/serverless-models, https://docs.together.ai/docs/inference/chat/reasoning, https://www.together.ai/pricing, https://www.together.ai/models/minimax-m3 (retrieved 2026-10-11).

## Sources & retrieval dates

- https://www.together.ai/models/gpt-oss-120b — 2026-10-11
- https://docs.together.ai/docs/serverless-models — 2026-10-11
- https://docs.together.ai/docs/inference/chat/reasoning — 2026-10-11
- https://www.together.ai/pricing — 2026-10-11
- https://www.together.ai/models/glm-5-3 — 2026-10-11
- https://www.together.ai/models/glm-5-3-flash — 2026-10-11
- https://www.together.ai/models/kimi-k3 — 2026-10-11
- https://www.together.ai/models/muse-glimmer — 2026-10-11
- https://www.together.ai/models/deepseek-v4-pro-0813 — 2026-10-11
- https://www.together.ai/models/minimax-m3 — 2026-10-11
