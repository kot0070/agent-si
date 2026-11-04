# Speed: Muse Spark through the API and Muse Glimmer on my PC

The team first ran on Muse Spark 1.3 Contributor through the Meta Model API. On November 2, 2026 my bank blocked the billing for that API, so I moved the demo to Muse Glimmer on my own PC. That decision was forced by the blocked card. It was not made for speed, and the local run is much slower.

## Muse Spark 1.3 Contributor, Meta Model API

Real run records from November 2, 2026.

| Task | Team | Time | Model calls |
|---|---|---|---|
| node-add: a small Node project with a test | On | 204 s | 10 |
| Create 1 file | On | 73, 80 and 117 s | 5 to 7 |
| Create 1 file | Off | 10 to 35 s | 1 to 3 |
| Append 1 line | On | 44 to 54 s | 5 |
| npm install | On | 60 to 235 s | 4 to 13 |

## Muse Glimmer, `muse-glimmer:30b` through Ollama on my PC

From [the run log](team-on-team-off-results.md).

| Task | Team | Time |
|---|---|---|
| node-add | On | 24 min 13 s, later 11.2 and 8.6 min |
| node-add | Off | 17 min 50 s |

## Why the local run is slow

The model is about 18 GB. My PC has an RTX 3070 with 8 GB of video memory and 32 GB of RAM, so the model does not fit in video memory and runs split with the CPU, at about 2.6 tokens per second. That is a limit of this PC. I did not measure Muse Glimmer on stronger hardware.

Runs also differ from each other: the Director's plan size varies, and a run can need repairs or a re-ask. So these numbers show the size of the gap, not an exact ratio.
