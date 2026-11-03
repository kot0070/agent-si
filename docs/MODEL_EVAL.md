# How the per-role reasoning level was chosen (MODEL_EVAL)

The app sends one reasoning level per agent role on muse-class models.
The levels below were picked by a small measured eval, not by guessing:
each candidate level ran the same fixed task set, a deterministic grader
scored every reply (no model grades anything), and the cheapest level
that stayed within 2 points of the best pass rate per role won (ties go
to the lower latency).

## What was measured

14 tasks, 3 repeats per (task, level) cell: director 4 (3 plan tasks with
a stated parts range + 1 plain question), worker 4 (single-turn file
tasks through the real action protocol), auditor 4 (finished parts, 2
seeded wrong), solo 2 (plain questions). Graders are the app's own
protocol parsers plus exact checks (parts count in range / exact
path+content / verdict match / expected word). Cost bills completion
tokens including reasoning, exactly like the app budget gate (USD 0.10
input / 0.20 output per 1M tokens, contributor tier).

| level | director pass@1 | worker pass@1 | auditor pass@1 | solo pass@1 | mean cost/attempt USD | median s | p90 s | blanks |
|---|---|---|---|---|---|---|---|---|
| none | 0.92 (11/12) | 0.25 (3/12) | 1.00 (12/12) | 1.00 (6/6) | 0.000438 | 14.390 | 44.470 | 1 |
| low | 1.00 (12/12) | 0.33 (4/12) | 1.00 (12/12) | 1.00 (6/6) | 0.000215 | 5.845 | 19.280 | 0 |
| medium | 0.92 (11/12) | 0.25 (3/12) | 1.00 (12/12) | 1.00 (6/6) | 0.000401 | 14.745 | 32.680 | 0 |
| high | 0.92 (11/12) | 0.33 (4/12) | 1.00 (12/12) | 1.00 (6/6) | 0.000488 | 15.865 | 41.630 | 1 |
| max | 0.92 (11/12) | 0.67 (8/12) | 1.00 (12/12) | 1.00 (6/6) | 0.000653 | 27.025 | 85.180 | 1 |

The set is small (14 tasks); no exact claim beyond the rows above.

## Decision per role

- director: low (cheapest level at the best 1.00 pass rate)
- worker: max (only level clearly above the rest: 0.67 vs 0.33)
- auditor: low (cheapest at the shared best 1.00)
- solo: low (cheapest at the shared best 1.00)

Before gridding, each level is probed live against the API in both wire
shapes; refused values are recorded and never gridded. The baseline
`none` sends no reasoning parameter at all (the old app behaviour).

## How to rerun

The eval ships with the checkout next to this doc, task set included:

```
python scripts/reasoning_eval.py [--workers 1..4] [--probe-only]
```

The key comes from the `AGENT_SI_EVAL_KEY` environment variable only
(put it in the child process env, never in argv, files, or logs); the
tool refuses to run without it. Reports land next to the script unless
`--out-json` / `--out-md` say otherwise. Offline checks (no key, no
network) that pin the graders, the cost math, the decision rule, and
the key hygiene:

```
python -m pytest tests/test_scripts_reasoning_eval.py
```
