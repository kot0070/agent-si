# Amazon Bedrock — KB (retrieved 2026-10-11)

## bedrock-anthropic-claude-fable-5-1

- Model ID: bedrock-anthropic-claude-fable-5-1 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Structured output: UNKNOWN (checked https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-06 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Release date: 2026-09-01 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on same frontier model inside AWS boundary, Bedrock guardrails and VPC controls.
- Weaknesses (analysis): watch out for top price tier, gated availability on some endpoints.
- Best for (analysis): suited to long-horizon agents on AWS, private VPC inference.
- Avoid for (analysis): less suited to cheapest bulk routing.
- Task fit (analysis): agents: best; coding: best; reasoning: best; routing: avoid.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-fable-5-1.
- Region note (analysis): global endpoint standard rate; regional endpoints carry ~10% premium per Anthropic docs.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-opus-5-5

- Model ID: bedrock-anthropic-claude-opus-5-5 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-06 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Release date: 2026-09-22 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on most capable Opus via Bedrock, global and regional endpoints.
- Weaknesses (analysis): watch out for regional 10% premium, Bedrock sets own lifecycle dates.
- Best for (analysis): suited to agentic coding on AWS, knowledge work with data residency.
- Avoid for (analysis): less suited to tiny-budget routing.
- Task fit (analysis): agents: best; coding: best; reasoning: best; routing: ok.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-opus-5-5.
- Region note (analysis): global.anthropic.claude-opus-5-5 at $4/$20; us./eu./au./jp. prefixes at $4.40/$22.00 per third-party cross-check rows (not a FACT source).
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-sonnet-5-5

- Model ID: bedrock-anthropic-claude-sonnet-5-5 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-06 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Release date: 2026-09-28 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on balanced cost and intelligence on AWS, batch inference 50% lower per Bedrock pricing.
- Weaknesses (analysis): watch out for regional premium applies, Bedrock lifecycle differs from first-party.
- Best for (analysis): suited to production agents on AWS, coding at scale with residency.
- Avoid for (analysis): less suited to deepest frontier reasoning.
- Task fit (analysis): agents: best; coding: best; reasoning: good; routing: good.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-sonnet-5-5.
- Region note (analysis): global endpoint standard rate; regional endpoints ~10% premium per Anthropic cloud pricing note.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-haiku-5-5

- Model ID: bedrock-anthropic-claude-haiku-5-5 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-06 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Release date: 2026-10-07 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on cheapest Claude on Bedrock, fastest latency class.
- Weaknesses (analysis): watch out for length-tiered pricing, weakest reasoning of family.
- Best for (analysis): suited to high-volume classification on AWS, extraction and routing fleets.
- Avoid for (analysis): less suited to frontier reasoning.
- Task fit (analysis): agents: good; coding: good; reasoning: ok; routing: best.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-haiku-5-5.
- Region note (analysis): base rate for prompts up to 100K tokens; higher tier over 100K per Anthropic pricing.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-opus-5

- Model ID: bedrock-anthropic-claude-opus-5 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-05 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Release date: 2026-07-24 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on Bedrock-hosted Opus 5, same base price as first-party.
- Weaknesses (analysis): watch out for superseded by Opus 5.5, UNKNOWN Bedrock regional table.
- Best for (analysis): suited to legacy Opus 5 agents on AWS.
- Avoid for (analysis): less suited to cheap bulk work.
- Task fit (analysis): agents: best; coding: best; reasoning: best; routing: ok.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-opus-5.
- Region note (analysis): standard rate; regional endpoints ~10% premium.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-sonnet-5

- Model ID: bedrock-anthropic-claude-sonnet-5 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-01 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Release date: 2026-06-30 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on cheap production Sonnet on AWS, batch discount eligible.
- Weaknesses (analysis): watch out for superseded by Sonnet 5.5, UNKNOWN Bedrock regional table.
- Best for (analysis): suited to legacy Sonnet production fleets on AWS.
- Avoid for (analysis): less suited to frontier reasoning.
- Task fit (analysis): agents: good; coding: best; reasoning: good; routing: good.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-sonnet-5.
- Region note (analysis): standard rate; regional endpoints ~10% premium.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-opus-4-8

- Model ID: bedrock-anthropic-claude-opus-4-8 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Context window: 1000000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Max output: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Knowledge cutoff: 2026-01 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Release date: 2026-05-28 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the strong-reasoning band for selection purposes.
- Strengths (analysis): reads as strong on stable legacy Opus on AWS, fast mode on first-party only.
- Weaknesses (analysis): watch out for two generations behind, UNKNOWN Bedrock regional table.
- Best for (analysis): suited to legacy 4.x Opus agents on AWS.
- Avoid for (analysis): less suited to cheap routing.
- Task fit (analysis): agents: best; coding: best; reasoning: best; routing: ok.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-opus-4-8.
- Region note (analysis): standard rate; regional endpoints ~10% premium.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-anthropic-claude-haiku-4-5

- Model ID: bedrock-anthropic-claude-haiku-4-5 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Context window: 200000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Max output: 64000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Modalities: ["text", "image"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Structured output: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Reasoning: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Knowledge cutoff: 2025-02 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Release date: 2025-10-16 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on cheap Bedrock-hosted lightweight, good tool-calling for size.
- Weaknesses (analysis): watch out for superseded by Haiku 5.5, UNKNOWN Bedrock regional table.
- Best for (analysis): suited to cheap efficient agents on AWS.
- Avoid for (analysis): less suited to frontier reasoning.
- Task fit (analysis): agents: good; coding: good; reasoning: ok; routing: best.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=anthropic, underlying model=anthropic.claude-haiku-4-5.
- Region note (analysis): standard rate; regional endpoints ~10% premium.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-meta-llama-3-3-70b

- Model ID: bedrock-meta-llama-3-3-70b (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Context window: 128000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Max output: 4000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Modalities: ["text"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Knowledge cutoff: 2023-12 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Release date: 2024-12-06 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Status: Legacy (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the balanced band for selection purposes.
- Strengths (analysis): reads as strong on open-weight flexibility, Bedrock VPC and guardrails apply.
- Weaknesses (analysis): watch out for UNKNOWN Bedrock per-token price, weaker than Claude Opus on code.
- Best for (analysis): suited to open-weight chat on AWS, cost-sensitive batch inference.
- Avoid for (analysis): less suited to frontier coding precision, tasks needing Claude tooling.
- Task fit (analysis): agents: ok; coding: ok; reasoning: ok; routing: good.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=meta, underlying model=meta.llama-3-3-70b-instruct.
- Region note (analysis): Bedrock lists Meta Llama 3.3 70B Instruct as supported; per-token table not captured 2026-10-11.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## bedrock-amazon-nova-pro

- Model ID: bedrock-amazon-nova-pro (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Context window: 300000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Max output: 10000 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Modalities: ["text", "image", "video"] (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Tool calling: true (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Structured output: false (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Reasoning: UNKNOWN (checked https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Knowledge cutoff: 2024-10 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Release date: 2024-12-05 (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Status: Active (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, retrieved 2026-10-11).
- Price input per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price output per 1M tokens: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price currency: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).
- Price date: UNKNOWN (checked https://aws.amazon.com/bedrock/pricing/, retrieved 2026-10-11).

- Family and tier (analysis): a UNKNOWN-family model, placed in the cheap-fast band for selection purposes.
- Strengths (analysis): reads as strong on AWS-native model, Bedrock batch and provisioned options.
- Weaknesses (analysis): watch out for UNKNOWN Bedrock per-token price, UNKNOWN benchmark standing.
- Best for (analysis): suited to AWS-native cheap inference, summarisation and RAG on Bedrock.
- Avoid for (analysis): less suited to frontier reasoning, Claude-specific tooling.
- Task fit (analysis): agents: ok; coding: ok; reasoning: ok; routing: best.
- Role notes (analysis): UNKNOWN.
- Speed class (analysis): UNKNOWN.
- Hosting (analysis): hosted mapping; hosts_family=amazon, underlying model=amazon.nova-pro.
- Region note (analysis): Bedrock lists Amazon Nova Pro as supported; per-token table not captured 2026-10-11.
Analysis basis: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html, https://aws.amazon.com/bedrock/pricing/ (retrieved 2026-10-11).

## Sources & retrieval dates

- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html — 2026-10-11
- https://aws.amazon.com/bedrock/pricing/ — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html — 2026-10-11
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html — 2026-10-11
