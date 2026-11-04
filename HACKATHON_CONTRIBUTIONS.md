# Hackathon contributions

Facts only. Each row names what is new in the product and where to check it.

## How this project uses Meta's models

Only Meta models run in the demo. Two setups, one after the other:

- **Until November 2, 2026: Muse Spark 1.3 Contributor** (`meta/muse-spark-1.3-contributor`) through the Meta Model API. Every role of the team ran on it.
- **After that: Muse Glimmer** (`muse-glimmer:30b`) on the same PC, through Ollama. On November 2 the Meta Model API billing was blocked, so the final demo runs locally.

What each role does, and which Meta model it used:

| Role | What it does | Muse Spark (Meta Model API) | Muse Glimmer (local) |
|---|---|---|---|
| Director | Plans the task, splits it into parts, checks the split | yes | yes |
| Manager | Owns one part and drives its workers | yes | yes |
| Worker | Writes the files and runs the commands | yes | yes |
| Auditor | A fresh instance per audit; reads the run and gives the verdict | yes | yes |
| Watcher | Observes the run by rules; a model answers only when the Watcher is pinned to one | only if the cloud fallback is on | yes, when pinned (it was pinned in the demo) |

Adapters for other providers exist in the code as an option. The demo does not call them. The app also lets you pick a reasoning level per role on Muse models; the levels were chosen by a small measured eval ([docs/MODEL_EVAL.md](docs/MODEL_EVAL.md)).

The app itself was also built with Muse Code agents, many at once: see [docs/HOW_IT_WAS_BUILT.md](docs/HOW_IT_WAS_BUILT.md) and [docs/CONTROLLING_MANY_AGENTS.md](docs/CONTROLLING_MANY_AGENTS.md).

Where to check each claim:

| Claim | Evidence |
|---|---|
| Muse Spark runs through the Meta Model API, first passes by the auditor | photos of the screen in [docs/EVIDENCE.md](docs/EVIDENCE.md) (section "First passes on Muse Spark") |
| Muse Glimmer runs the whole team locally, with timing, verdict and tokens | [docs/evidence/video-run-timing.md](docs/evidence/video-run-timing.md) |
| Team On and Team Off results on Muse Glimmer | [docs/evidence/team-on-team-off-results.md](docs/evidence/team-on-team-off-results.md) |
| With every role on Muse Glimmer, the app talks only to this PC | [docs/evidence/network-proof.md](docs/evidence/network-proof.md) |
| The Meta rows and the model list in the app | [docs/EVIDENCE.md](docs/EVIDENCE.md), [docs/MODEL_EVAL.md](docs/MODEL_EVAL.md) |
| The demo video | https://youtu.be/Mf_OHejanns |

## What else is new in the product

| contribution | where to check |
| ------------ | -------------- |
| Check an idea text against the public text rules: the app serves the rules and reports violations [PROVEN: public-text routes and rules file] | `src/agent_si/backend/k12open1_routes.py`, `src/agent_si/backend/public_text.py` |
| Scan files and notes for secrets and private paths before you submit them [PROVEN: scan route and secret-scan file] | `src/agent_si/backend/k12open1_routes.py`, `src/agent_si/backend/secretscan.py` |

The demo video is on YouTube (link above). The old draft script and scene plan were removed from the repo; they are still in git history.

Test counts and auditor verdicts of the final build are in [docs/evidence/final-gate-summary.md](docs/evidence/final-gate-summary.md), including what failed there.
