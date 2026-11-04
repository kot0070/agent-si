# The final demo video, scene by scene

Video: https://youtu.be/Mf_OHejanns, 2:55, in the owner's voice. All 14 main functions have a scene. They are not all shown the same way, so the last column says which is which:

- **Live:** the action really happens on screen, on Muse Glimmer through Ollama on this PC.
- **Run result:** the real records of a finished run on that model.
- **Screen:** the function's real screen in the app. The action itself is not performed in the video.

| Scene | Time | What is on screen | How it is shown |
|---|---|---|---|
| Opening | 0:00-0:08 | The first screen of the app and the project. | Screen |
| F04 Autonomous development | 0:08-0:48 | One task: Director plan, Manager, Worker, 4 checks, Auditor, "Done - 1 part, 1 passed". | Live, sped up 13x, labelled, with the real clock on screen |
| Earlier Muse Spark runs | 0:48-0:56 | Two photos of a screen: runs on Muse Spark 1.3 Contributor, auditor PASS, run success. | Photos from November 2, labelled "not live" |
| F01 Code tests | 0:56-1:04 | Code checks and the auditor verdict in the run log, then the Tests tab with its code, AI and human tests. | Run result and screen |
| F02 Fixed team | 1:04-1:16 | Role pools with each role pinned to `muse-glimmer:30b`, and the same team in the project chat. | Screen |
| F03 Auto team | 1:16-1:25 | A role set to Automatic, the optimization weights, and the stored reason for the router's choice. | Screen |
| F08 Provider catalog | 1:25-1:31 | Provider cards with Connect. No key is typed and nothing is connected. | Screen |
| F05 Team control panel | 1:31-1:40 | Runs, tokens by role and model, and cost. | Run result |
| F06 Watcher | 1:40-1:52 | Model calls 1, model tokens 299, a journal row with an ESCALATE decision and the check script it named. | Live call on the local model, shown after it happened |
| F07 Emergency Stop | 1:52-1:59 | A running task, a real click on Stop all, then "Stopped by you". | Live, real time |
| F10 Local AI benchmark | 1:59-2:12 | A real Quick benchmark, then measured rows and a decision record line. | Live, sped up 61x, labelled |
| F12 Budget and caps | 2:12-2:19 | Cost 0 of 5.00 USD and the spend cap field per provider. | Screen |
| F09 Model knowledge base | 2:19-2:27 | Knowledge base versions with Update, Check online and From file. No update is performed. | Screen |
| F11 Knowledge bases | 2:27-2:35 | The attach form and "No knowledge base is attached to this project." | Screen |
| F13 Install permission | 2:35-2:41 | The install grants list, empty. No install request appears in the video. | Screen |
| F14 Clean install | 2:41-2:48 | A second app window on an empty data folder: welcome screen, no project. | Live |
| Closing | 2:48-2:55 | The project with its finished run. | Run result |

The F04 run is the one timed in [video-run-timing.md](video-run-timing.md). That file was written for an earlier 2:57 cut, so its scene times and speed-up factors differ from this table. Open issues seen while filming are in [Known issues](../KNOWN_ISSUES.md).
