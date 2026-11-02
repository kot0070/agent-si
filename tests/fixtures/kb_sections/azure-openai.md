# Azure OpenAI — KB (retrieved 2026-10-11)

## gpt-6-astra

- Model ID: gpt-6-astra (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 1050000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2026-09-03 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-6-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on Azure-hosted OpenAI GPT-6 flagship; same weights as OpenAI, Azure SLA, VNet/data-residency, billed via Azure subscription.
- Weaknesses (analysis): watch out for Azure pricing separate; short/long context categories; quota tiers may need request.
- Best for (analysis): suited to complex reasoning in Azure compliance boundary.
- Avoid for (analysis): less suited to outside-Azure low-cost bulk.
- Task fit (analysis): code-gen: best; planning: best; math-reasoning: best; agent-loop: best; long-doc: best.
- Role notes (analysis): director role: Use when data must stay in Azure.; manager role: Deploy via Foundry standard/provisioned.; worker role: Same prompts as OpenAI endpoint.; auditor role: Audit with residency guarantees..
- Speed class (analysis): slow.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-6-astra.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-6.1-sol

- Model ID: gpt-6.1-sol (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 1050000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2026-09-29 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-6.1-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI 6.1-sol; balanced cost/intelligence.
- Weaknesses (analysis): watch out for Azure billing separate from OpenAI API.
- Best for (analysis): suited to balanced Azure workloads.
- Avoid for (analysis): less suited to UNKNOWN.
- Task fit (analysis): code-gen: best; planning: best; short-chat: best; long-doc: best; agent-loop: best.
- Role notes (analysis): director role: Default Azure reasoning.; manager role: Standard deployment.; worker role: Primary Azure worker.; auditor role: Azure audit trail..
- Speed class (analysis): medium.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-6.1-sol.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-6-luna

- Model ID: gpt-6-luna (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 1050000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2026-09-22 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-6-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI Luna efficient tier.
- Weaknesses (analysis): watch out for UNKNOWN.
- Best for (analysis): suited to high-volume Azure tasks.
- Avoid for (analysis): less suited to UNKNOWN.
- Task fit (analysis): routing: best; short-chat: best; bulk-summary: best.
- Role notes (analysis): director role: Cheap Azure triage.; manager role: Bulk fan-out.; worker role: Bulk worker.; auditor role: First pass..
- Speed class (analysis): fast.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-6-luna.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-5.6-sol

- Model ID: gpt-5.6-sol (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 1050000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2026-07-09 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-5.6-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI 5.6-sol flagship.
- Weaknesses (analysis): watch out for UNKNOWN.
- Best for (analysis): suited to professional Azure reasoning work.
- Avoid for (analysis): less suited to UNKNOWN.
- Task fit (analysis): code-gen: best; planning: best; math-reasoning: best; long-doc: best.
- Role notes (analysis): director role: Fallback when GPT-6 quota limited.; manager role: Stable Azure pipeline.; worker role: Strong worker.; auditor role: Reliable audit..
- Speed class (analysis): medium.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-5.6-sol.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-5.4

- Model ID: gpt-5.4 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 1050000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2026-03-05 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-5.4-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI 5.4 generation.
- Weaknesses (analysis): watch out for UNKNOWN.
- Best for (analysis): suited to general Azure chat and docs.
- Avoid for (analysis): less suited to UNKNOWN.
- Task fit (analysis): short-chat: best; long-doc: good; code-gen: good.
- Role notes (analysis): director role: Legacy compat.; manager role: Existing pipelines.; worker role: General tasks.; auditor role: Routine audits..
- Speed class (analysis): medium.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-5.4.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-4o

- Model ID: gpt-4o (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 16384 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2024-11-20 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-4o-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI GPT-4o omni; mature.
- Weaknesses (analysis): watch out for 128K context smaller than 5/6 gen.
- Best for (analysis): suited to general multimodal Azure apps.
- Avoid for (analysis): less suited to hard reasoning.
- Task fit (analysis): short-chat: best; vision: best; code-gen: good.
- Role notes (analysis): director role: Legacy default.; manager role: Stable apps.; worker role: Everyday worker.; auditor role: Baseline..
- Speed class (analysis): medium.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-4o.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-4o-mini

- Model ID: gpt-4o-mini (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 128000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 16384 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2024-07-18 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a gpt-4o-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI mini cheap tier.
- Weaknesses (analysis): watch out for UNKNOWN.
- Best for (analysis): suited to high-volume cheap Azure traffic.
- Avoid for (analysis): less suited to frontier proofs.
- Task fit (analysis): routing: best; short-chat: best; bulk-summary: best.
- Role notes (analysis): director role: Bulk triage.; manager role: Fan-out.; worker role: Cheap worker.; auditor role: First pass..
- Speed class (analysis): fast.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-4o-mini.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## o3

- Model ID: o3 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 200000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: 100000 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "image-in", "text-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: true (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: 2024-05-31 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: 2025-04-16 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a o-series-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI o3 reasoning.
- Weaknesses (analysis): watch out for migration to gpt-5.6-sol advised by OpenAI.
- Best for (analysis): suited to Azure math/science reasoning.
- Avoid for (analysis): less suited to cheap chat.
- Task fit (analysis): math-reasoning: best; code-gen: best; planning: best.
- Role notes (analysis): director role: Deep escalation.; manager role: Multi-step.; worker role: Reasoning chains.; auditor role: Verify logic..
- Speed class (analysis): slow.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=o3.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## text-embedding-3-large

- Model ID: text-embedding-3-large (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: 8192 (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "vector-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a embeddings-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI embedding; same 3072-dim model.
- Weaknesses (analysis): watch out for must re-embed when migrating from ada.
- Best for (analysis): suited to Azure RAG retrieval.
- Avoid for (analysis): less suited to generation.
- Task fit (analysis): embeddings: best; long-doc: good; routing: good.
- Role notes (analysis): director role: Similarity routing.; manager role: RAG backbone.; worker role: Embed first.; auditor role: Duplicate checks..
- Speed class (analysis): fast.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=text-embedding-3-large.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## gpt-4o-mini-tts

- Model ID: gpt-4o-mini-tts (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Context window: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Max output: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Modalities: ["text-in", "audio-out"] (https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Tool calling: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Knowledge cutoff: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Release date: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Status: UNKNOWN (checked https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

- Family and tier (analysis): a speech-family model, placed in the specialised band for selection purposes.
- Strengths (analysis): reads as strong on Azure host of OpenAI TTS voice.
- Weaknesses (analysis): watch out for Azure audio availability varies by region.
- Best for (analysis): suited to Azure voice output.
- Avoid for (analysis): less suited to reasoning.
- Task fit (analysis): speech: best.
- Role notes (analysis): director role: Voice only.; manager role: Voice chain.; worker role: Narration.; auditor role: UNKNOWN.
- Speed class (analysis): fast.
- Hosting (analysis): hosted mapping; hosts_family=openai, underlying model=gpt-4o-mini-tts.
Analysis basis: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models, https://azure.microsoft.com/en-us/pricing/details/azure-openai/ (retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).
- Price note: Azure hub exposes no static per-model token rates (JS calculator); kept UNKNOWN per K3 special (b). (catalog sources_checked_note; checked https://azure.microsoft.com/en-us/pricing/details/azure-openai/, retrieved 2026-10-11).

## Sources & retrieval dates

- https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models — 2026-10-11
- https://azure.microsoft.com/en-us/pricing/details/azure-openai/ — 2026-10-11
