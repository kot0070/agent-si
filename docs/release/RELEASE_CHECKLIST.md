# Release checklist - morning release runbook

This runbook freezes and publishes one morning release of the desktop build.
Work every section in order and fill each RECORD-AT-RELEASE value during the
run. Never invent or reuse a value from an older run: a missing value blocks
sign-off instead of being guessed.

Each release step is one row that starts with a pipe character. Row column
order is step id, area, record or command, expected evidence, verdict source.
The trace metric at the end of this file counts those rows.

## 1 - Preflight sync

Fetch the integration line and confirm this checkout matches it before doing
any release work. A mismatch blocks the run at once.

| S01 | preflight sync | command: fetch origin, then confirm HEAD equals origin/int | expected: HEAD matches origin/int with empty status output (write-time base int a8b5a57) | verdict: lane preflight record |
| S02 | preflight tree | command: status check for uncommitted changes | expected: no uncommitted changes; the checklist is the only new file | verdict: lane preflight record |
| S03 | preflight seams | command: read-only presence check of tools/start.py and the old demo script draft (removed from the repo later, see git history) plus absence check of the build-time packaging manifest folder | expected: seams present unedited; manifest folder absent at run time BLOCKS sign-off | verdict: lane STEP-0 seam check |

## 2 - Unsigned build line

The build is unsigned, so the release notes must say so plainly directly above
the published hashes. The exact line lives in step S04 only.

| S04 | unsigned line | record: release notes carry the exact line this build is not code-signed - verify the SHA256 below | expected: the exact line appears once above the published hashes | verdict: INSTALLB brief R5 |
| S05 | unsigned publish | record: SHA256 of AgentSI.exe and of the portable zip published with the release | expected: both hashes printed next to the unsigned line | verdict: INSTALLB brief R5 |

## 3 - Hash x4 equality

All four hash records must hold equal values before anything ships. Every
manifest value is written only by script from real values, never by hand.

| S06 | hash exe | record: SHA256 computed from the staged folder exe dist/stage/AgentSI.exe | expected: RECORD-AT-RELEASE value stored in the release record | verdict: INSTALLB brief R5 |
| S07 | hash portable | record: SHA256 computed from the portable zip | expected: RECORD-AT-RELEASE value stored in the release record | verdict: INSTALLB brief R5 |
| S08 | hash manifest | record: MANIFEST.json runtime file list for the staged folder plus the in-zip SHA256SUMS index covering every zip member | expected: MANIFEST entry for the folder exe plus per-member zip hashes equal S06 and S07 | verdict: INSTALLB brief R5 and R9 |
| S09 | hash x4 equality | record: folder-exe value plus zip value plus setup value plus MANIFEST entries plus HASH.json plus the canonical HASH.json.sha256 file | expected: all values recorded and printed together with both SHA256SUMS indexes agreeing | verdict: INSTALLB brief R5 |

## 4 - Manifest license notices evidence

The bundle must carry its paperwork: the manifest, the licence and the
third-party notices, plus the evidence index.

| S10 | manifest evidence | record: MANIFEST.json in the build-time installer manifest folder with the sha list | expected: every runtime file listed with hash and byte count; absent at run time BLOCKS sign-off | verdict: INSTALLB brief R9 |
| S11 | license evidence | record: MIT LICENSE screen in the installer plus the copyright line in exe metadata | expected: installer cites the unsigned build and shows LICENSE; metadata carries the copyright line | verdict: INSTALLB brief R7 |
| S12 | notices evidence | record: third-party notices listing pywebview plus pythonnet plus clr_loader plus bottle plus proxy_tools with their licences, plus the evidence index | expected: notices files in the bundle and every R9 index entry present | verdict: INSTALLB brief R7 and R9 |

## 5 - Function evidence F01 to F14

Every release claim maps to one evidence line from the drive defects file.
A claim with no evidence line stays PENDING-REDRIVE and never ships as proven.
Non-LIVE rows below name their PENDING-REDRIVE gate explicitly.

| S13 | F01 catalog run | record: catalog run of suite catalog-frozen-v1 | expected: 200 ok with 6 runs in local, AI, human order, all PASS with evidence refs | verdict: DEFECTS F01 line, LIVE |
| S14 | F02 pinned hierarchy | record: five roles pinned to the bare model with a hierarchy run | expected: 200 profiles and a run record with gate and audit refs | verdict: DEFECTS F02 line, LIVE-note |
| S15 | F03 auto routing | record: routing auto probe plus provider models probe plus decide call | expected: 422 AUTO BLOCKED with no KB rows for the connected model and the why-record kept; auto-routing claims stay PENDING-REDRIVE | verdict: DEFECTS F03 lines, FAIL |
| S16 | F04 full chain | record: plan, start, advance, run, fresh-audit, finish, finalize sequence | expected: terminal verdict BLOCKED with NO_ELIGIBLE_AUDITOR and PASS verification records kept | verdict: DEFECTS F04 line, LIVE-gaps |
| S17 | F05 control panel | record: control-plane map probe during a run | expected: static function map only, so live team claims stay PENDING-REDRIVE | verdict: DEFECTS F05 line, FAIL |
| S18 | F06 watcher journal | record: watcher journal read before and after a full run | expected: no run entries appear, so journal claims stay PENDING-REDRIVE | verdict: DEFECTS F06 line, FAIL |
| S19 | F07 stop all | record: stop-all call with actor and project plus session token | expected: 200 accepted with stopped count zero and the journal receipt kept | verdict: DEFECTS F07 line, SPLIT receipt LIVE |
| S20 | F08 provider online | record: providers list probe | expected: 200 with the meta provider evidenced online and no key handled | verdict: DEFECTS F08 line, LIVE |
| S21 | F09 model KB | record: models list plus KB refresh proposal and apply probes | expected: models list LIVE with refresh apply rejected, so KB-update claims stay PENDING-REDRIVE | verdict: DEFECTS F09 line, SPLIT |
| S22 | F10 local bench | record: local status plus bench check probes | expected: NOT_CONFIGURED with reachable false, recorded as BLOCKED-ENV | verdict: DEFECTS F10 line, LIVE-record |
| S23 | F11 KB attach | record: KB attach call plus keyed chats | expected: attach 200 for role-shaped KB while chats answer from the model, so KB-grounded chat claims stay PENDING-REDRIVE | verdict: DEFECTS F11 lines, SPLIT |
| S24 | F12 budget | record: budget read before and after keyed chats plus ledger read | expected: spent stays zero with an empty ledger and empty per-provider caps, so spend claims stay PENDING-REDRIVE | verdict: DEFECTS F12 lines, SPLIT |
| S25 | F13 permission once | record: permissions check called twice for the same tool | expected: asked_once false then true with the persisted record verified | verdict: DEFECTS F13 line, LIVE-record |
| S26 | F14 clean smoke | record: start.py smoke run on a fresh store with a memory secret store | expected: exit zero with openapi 200 and a fresh store holding only the catalog and audit seeds | verdict: DEFECTS F14 line, LIVE |

## 6 - Demo scene

The release demo follows the merged script exactly: one 3-minute cut over all
14 functions, opening with F04 and closing with F14.

| S27 | scene script | record: merged demo script draft (removed from the repo later, see git history) at int merge 6c01765 | expected: 14-function 3-minute shape with click labels present | verdict: lane scene-shape brief |
| S28 | scene run | record: performed demo cut timed at 174 seconds or less | expected: on-screen state and voice-over per script row | verdict: K12DEMO3 script |

## 7 - Clean-profile double proof

Two independent proofs are required: the smoke entry on a fresh store and the
first start of the frozen exe on an empty profile.

| S29 | clean smoke | command: python tools/start.py --smoke --tag RECORD-AT-RELEASE --data-dir RECORD-AT-RELEASE with a memory secret store | expected: exit zero, openapi 200, fresh store with only catalog and audit seeds | verdict: DEFECTS F14 line |
| S30 | clean exe start | record: first start of AgentSI.exe on an empty profile | expected: empty store asserted with a native window and no console | verdict: INSTALLB brief R4 and R6 |

## 8 - Owner-only steps

The two steps below are performed by the owner only. The release operator
prepares everything else and then hands these over.

| S31 | OWNER-only public repo | record: public-repo publish performed by the owner | expected: repo tag plus release page carrying the unsigned line and both SHAs | verdict: owner record, OWNER-only |
| S32 | OWNER-only video upload | record: demo video upload performed by the owner | expected: uploaded cut matches the S27 script | verdict: owner record, OWNER-only |

## 9 - Trace metric and sign-off

Trace metric: the count of lines starting with a pipe character equals the
release-step row count. Recompute it with the HD-CHECK pipe counter before
sign-off and record the number here: RECORD-AT-RELEASE.

Sign-off: the operator initials and dates each section above, then the owner
countersigns S31 and S32 after the OWNER-only steps complete.
