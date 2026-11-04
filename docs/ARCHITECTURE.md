# Architecture — Agent SI

## Overview

A React shell inside a desktop window talks over loopback HTTP and events to a local backend. The backend runs the engine: plan, split, work, check, audit. Providers are called only with stored references. Records stay in the app data folder.

```
[React shell + desktop window]
        |  HTTP + events over loopback
[Backend service]
  chat -> manager -> model call -> connected provider
  Director -> Managers -> workers -> checks -> fresh auditor
  routing + Auto | budget | watcher | knowledge base
        |
[App data folder: projects, tasks, runs, decisions, audits, journal]
[Windows Credential Manager: keys only]
```

## Shell and backend

- Shell: React single-page app with routes for chat, live agents, watcher, projects, project views, settings, first run, about, migration, and how-it-works. Served locally and shown in the desktop window.
- Backend: local service that owns projects, tasks, runs, ledger, budget, providers, routing, watcher, and knowledge-base links. The chat stream goes through a manager bridge into the model call and back as events.
- Models: hosted providers over HTTPS, or a local server such as Ollama on the loopback address. With every role on a local model the app talks only to this PC: [network proof](evidence/network-proof.md).

## Engine

- Director: plans the task, splits it into parts, checks the split, and integrates the results.
- Managers: each owns a part of the plan and drives its workers to completion.
- Workers: small task agents that write files and run the assigned steps. Work runs in sequence unless a step explicitly allows parallel parts.
- Auditor: a fresh instance per audit. It reads the run, checks the files and records, and returns a verdict. Audit records are stored with the run and shown in the project view.

## Routing and Auto

Routing picks which connected model does each role. Each role can be pinned to a fixed model or set to Auto. Auto picks the cheapest fitting connected model from the known price list and records why it chose it. The decision, the reason, and the model stay with the run. If no fitting model is connected, the request is blocked with a plain message instead of guessing.

## Budget

One gate per project with a currency, a soft limit, and a hard limit. Spend is reserved before work and settled after. When the hard limit is reached, new work is blocked and the ledger shows what was spent. Per-provider caps are shown on the same screen.

## Watcher

An independent observer with rules, a tick cycle, and a journal. It can nudge, restart supervised work, or run a scripted action within its permissions. Every action is written to the journal with state, model, and last action visible on the Watcher screen and the right cards.

## Knowledge base

Two stores work together: a model capability store (what each model is evidenced to do, with a refresh proposal flow) and attachable knowledge bases (project files attached to a run after validation). Chat can read a short context prefix from the attached base. Updates that need a connected provider are refused with a plain message when none is online.

## Data and secrets flow

The shell never holds key material. Writes that need a key go through the backend, which reads the key from the OS store by reference and sends it only to the selected provider endpoint. Redaction runs on logs, stored chat text, telemetry, and exported traces before anything is written or sent.
