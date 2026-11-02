# Model KB — index & how to use (updated 2026-10-11)

## How to read this KB

Read this index first. Never read the whole KB: load only the sections of the providers connected to the app, plus the matching entries of `task-guide`.
Total: 132 models across 16 providers (per STAGED model_catalog index.json, retrieved 2026-10-11).

## Provider table

- openai: 12 models — section `openai` (file openai.json).
- azure-openai: 10 models — section `azure-openai` (file azure-openai.json).
- anthropic: 12 models — section `anthropic` (file anthropic.json).
- bedrock: 10 models — section `bedrock` (file bedrock.json).
- google: 8 models — section `google` (file google.json).
- mistral: 8 models — section `mistral` (file mistral.json).
- meta: 7 models — section `meta` (file meta.json).
- xai: 7 models — section `xai` (file xai.json).
- deepseek: 4 models — section `deepseek` (file deepseek.json).
- cohere: 7 models — section `cohere` (file cohere.json).
- perplexity: 6 models — section `perplexity` (file perplexity.json).
- groq: 7 models — section `groq` (file groq.json).
- together: 7 models — section `together` (file together.json).
- fireworks: 7 models — section `fireworks` (file fireworks.json).
- openrouter: 6 models — section `openrouter` (file openrouter.json).
- local: 14 models — section `local` (file local.json).

## Partial-reading map

Hosts and aggregators (`azure-openai`, `bedrock`, `groq`, `together`, `fireworks`, `openrouter`) map to underlying model families; their sections list hosted-model ids with hosting notes (analysis). `local` covers offline families with sizing notes (analysis).
Cost-saving rule: the Director role picks the cheapest tier whose `task_fit` for the task is `best` or `good`; full per-role rules live in `task-guide`.

## Sources & retrieval dates

- Catalog counts: STAGED model_catalog/index.json — 2026-10-11.
- Per-provider files: STAGED model_catalog/<provider>.json — 2026-10-11.
