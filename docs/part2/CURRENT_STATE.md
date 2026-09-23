# FaultLab: verified current state

This is the preserved pre-implementation audit. For the latest September 20 implementation and experiments, read [Phase 3 results](PHASE3_RESULTS.md) and [the current checklist](PHASE3_TASKS.md). [Phase 2](PHASE2_RESULTS.md) and [Phase 1 results](PHASE1_RESULTS.md) preserve the preceding work.
Audit date: **September 20, 2026**. Source revision: **cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe**. Local `main` matched GitHub's HEAD and the working tree was clean before this report was added.

Start with the [30-day plan](PLAN.md). This report supplies its evidence. [Research notes](RESEARCH.md) explain the outside work considered.

## What the project is

FaultLab tests an agent that changes things through tools. It deliberately makes a test service fail, checks what actually happened, reproduces a mistake, asks a model for a bounded recovery rule, and tests that rule before accepting it.

The current task is **upgrade a synthetic order and send one truthful simulated confirmation**. The shop is a purpose-built, working test environment. FaultLab does not automatically build a correct environment or a trustworthy checker for any arbitrary agent.

The learning artifact is a versioned recovery policy, not new model weights. The fixed Referee compares private simulator state and the agent's original report. Neither the Mechanic nor Aria can decide that its own repair passed.

**The testing machinery works. The complete learned-improvement claim remains unproven.** No generated policy has passed through promotion. This does not make the failure-finding and evidence work worthless, but it changes what we can honestly demonstrate.

## What was checked

The audit covered the original specification and checklist, planning brief, current application modules, tests, Git history, Codex/Claude handoffs, result documents, local SQLite records, and relevant public papers and tools. Three parallel reviews examined the learning engine, product/integration boundaries, and external research. Findings were reconciled against the current source rather than treating historical handoffs as instructions or present-tense facts.

Fresh verification on this date:

| Check | Result |
|---|---|
| Backend tests | 367 passed; one dependency deprecation warning |
| Frontend unit tests | 25 passed |
| Production frontend build | Passed |
| Browser fixture tests | 3 passed |
| Optional fresh local execution test | Skipped; no new campaign requested for this audit |
| Backend, simulator, frontend HTTP responses | Ports 8000, 8001 and 5173 returned 200 |
| Active campaign | None |
| New provider calls or deployment | None |

Command: `env -u FAULTLAB_BROWSER_LOCAL ./scripts/test.sh`. Offline tests and browser fixtures establish software behavior under their test conditions; they are not new live learning evidence.

The running backend reports V3.1 as Actor and V4 Pro as the lab model, with no `models` map. The current source emits that map and the launcher defaults to Llama 3.1 8B as Actor. The running process therefore appears to predate the latest source. Do not mistake an old running server for verification of the checked-in launcher/configuration. A controlled restart and explicit configuration check belong before the next experiment. The app should be opened at `http://127.0.0.1:5173/`, not by opening Vite's `index.html` as a file.

## Saved experimental evidence

These counts came from read-only queries of `artifacts/lab.sqlite3`, not estimates from the README. They describe local records as of this audit; remote Weave records were not fetched again.

| Record | Count / state |
|---|---|
| Campaigns | 25: 12 NO_CHANGE, 8 COMPLETED, 2 STOPPED, 2 ERROR, 1 IDLE |
| Episodes | 571 across all stages and profiles |
| Model calls reported by campaign accounting | 3,696; excludes separate compatibility probes |
| Episode verdicts | 285 COMPLETED, 249 VIOLATION, 21 SAFE_UNRESOLVED, 7 CORRECTLY_REJECTED, 9 LAB_ERROR |
| Stored verified Weave evidence bundles | 529 |
| Generated candidate policy versions | 10 REJECTED, representing four distinct policy hashes |
| Accepted generated policies / promotion decisions | 0 / 0 |
| Final audit results / external transfer results | 0 / 0 |
| Registered agents | 14 records, all FaultLab reference registrations |
| Saved fresh regression executions / regression datasets | 0 / 0 |

The aggregate episode totals mix offline runs, discovery, repeated failures, interventions and candidate tests. **Do not turn 285/571 into a product accuracy score.** These are deliberately different, adaptively selected populations. Likewise, a campaign marked COMPLETED can be an ordinary baseline, not a successful learning campaign.

### The strongest completed baseline

[baseline-results.md](../baseline-results.md) records 36 predeclared trials: 18 real Llama 3.3 70B trials and 18 handwritten reference trials. The model completed 13 tasks, correctly rejected three and violated checks twice. The handwritten reference completed 15 and correctly rejected three. All 30 scheduled fault trials triggered. This is a useful baseline comparison; the reference is not a model-generated repair.

### The three important repair runs

| Campaign prefix | What happened | What it does not prove |
|---|---|---|
| `44085f54` | 143 episodes, 995 calls, 143 verified bundles. A supported diagnosis, generated policy, one 3/3 source pass, and a challenge that broke it. Three proposals had identical content; source passes were 1/3, 3/3, 2/3. | The 3/3 sample was not a new improved policy. No promotion ran. |
| `aa790230` | V3.1 Actor / V4 lab; 60 episodes, 415 calls, 60 verified bundles. Four identical proposals, source passes 2/3, 2/3, 2/3, 1/3. | Stronger proposal model did not solve convergence. No challenge ran. |
| `eb1bcf7e` | Later than the main Claude handoff: 106 episodes, 737 calls, 101 verified bundles; 45 task completions, 60 violations, one request timeout. Three proposals with two distinct hashes; no challenge. | The last historical run also did not produce an accepted repair. |

The split-role run did show a promising local effect: candidate trials completed 7/12 versus 0/12 for their paired incumbents. Five candidate trials still failed to produce a valid final report after the useful business actions succeeded. This is evidence worth investigating, not a completed independent improvement result.

See [learning-results.md](../learning-results.md) for the first two runs and retained local records for the later run. None of these saved campaigns validates every later configuration/runtime change in the current source.

## What Claude's work contributed

The Claude handoff is not a separate abandoned implementation to copy over. Its substantive changes are already in Git, especially `f21b970` (Shree author, Claude coauthor). Later `e60bedf` (Aryan author, Cursor coauthor) extends the model configuration and runtime. Attribution is based on Git metadata and the recorded handoff, not an assertion about who wrote each line.

Keep these contributions:

- Separate Actor and Explorer/Mechanic models, with role-aware settings and accounting.
- Better Explorer context about faults that were not reached.
- Diagnosis context containing already-observed reduction/control outcomes.
- Actual live repair/source-validation/challenge results and preserved negative outcomes.
- Later role-specific configuration, budget changes, UI improvements and sponsor records.

Several historical instructions are obsolete: the handoff says 28 changes are uncommitted; they are now committed. It says the freeze omits the lab model; current [freeze.py](../../backend/app/cli/freeze.py) includes the role map. It calls Aria deferred; later sponsor evidence records automatic invocation and observed completion.

## Capability status

| Area | Current status |
|---|---|
| Stateful synthetic services | Implemented and tested: isolated worlds, operation identity, delayed effects, lost replies, stale reads, transient failures |
| Fixed correctness checks | Implemented and tested, including truthful reporting and private-state evidence |
| Discovery → reproduce → reduce → diagnose | Implemented; these stages have live evidence |
| Generate repair → source test → challenge | Implemented; live evidence includes a challenge rejecting a proposed repair |
| Independent promotion and restart with learned policy | Software exists and offline tests cover paths; no qualifying live policy yet |
| Weave traces and baseline evaluation | Used live; stored readback evidence exists; a classification defect remains |
| Aria | Automatic dispatch and observed analysis documented; capture is partly operator-mediated, and reliable end-to-end completion handling remains unfinished |
| External smolagents integration | Real native-loop adapter and registration CLI exist; offline conformance tested; no live external registration or transfer result in this database |
| Regression runner and bundle validation | Implemented and tested; the learning loop reaches export too late to make current failures useful |
| Dashboard | Implemented with saved evidence, controls, dark/light mode, policy and experiment panels |
| General task onboarding | Not implemented; task semantics and checks are tied to the order workflow |
| Shared hosted execution product | Not implemented; current API is a local operator application |

## Confirmed engineering gaps

| Priority | Finding | Evidence / consequence |
|---|---|---|
| P0 | Incomplete patch execution contract | [diagnosis.py](../../backend/app/lab/diagnosis.py), lines 7–9, omits precise hook timing. `before_final_report` runs only after a report is proposed; a rule placed there cannot rescue a missing report. |
| P0 | Identical proposals get new qualification attempts | [learning.py](../../backend/app/lab/learning.py), lines 89–110; [policies.py](../../backend/app/lab/policies.py), lines 22–27. Repeated sampling can produce a lucky pass without a changed repair. |
| P0 | Challenge feedback loses context | [learning.py](../../backend/app/lab/learning.py), line 122, omits candidate content/hash and the challenge recipe already saved by [challenge.py](../../backend/app/lab/challenge.py). Each proposal request starts fresh. |
| P0 | Experiment identity excludes important algorithms | [configuration.py](../../backend/app/lab/configuration.py), line 37, omits learning/diagnosis/challenge/promotion/coordinator implementation hashes. Acceptance logic can change without changing the relevant configuration identity. |
| P0 | Actor failure is mislabeled in Weave | [tracing.py](../../backend/app/telemetry/tracing.py), lines 66–72, marks escaping report errors as LAB_ERROR; the local Referee can classify the same episode as a completed violation. Readback equality currently does not establish lifecycle-label equality. |
| P0 | A source becoming flaky looks like repair rejection | [learning.py](../../backend/app/lab/learning.py), lines 104–108, does not separately classify an incumbent that stops reproducing. Preserve candidate failures, but distinguish the experimental causes. |
| P1 | No useful export until promotion evaluation | [learning.py](../../backend/app/lab/learning.py), lines 125–131. [RegressionCompiler](../../backend/app/lab/regressions.py) already supports rejected policies, so export can be separated from promotion without manufacturing an accepted policy. |
| P1 | Incomplete shareable recording | [client.py](../../backend/app/cli/client.py), lines 89–99, omits event timelines and can omit rejected candidates/proposals. UI playback still relies on the original database. |
| P1 | Weak operational diagnostics | [coordinator.py](../../backend/app/lab/coordinator.py), lines 184–185, discards the underlying exception. `/api/health` checks only the backend process, not simulator readiness. |
| P1 | Aria publication can remain permanently uncertain | [aria_bridge.py](../../backend/app/telemetry/aria_bridge.py), lines 41–71. A durable intent is written before upload, but any prior intent blocks a new attempt. Reconciliation must distinguish not sent, sent, and unknown. |
| P1 | External onboarding is incomplete | Campaign creation always uses the reference registration. The external CLI exists, but the UI has no campaign agent choice and no guided setup. |
| P1 | Release packaging is incomplete | No tracked CI workflow, container setup or top-level project license was found. Fresh-clone demonstration depends on local credentials/history unless an evidence sample is shipped. |

Missing contract information is a plausible contributor to ineffective repair. It is **not proof that one prompt edit guarantees promotion**. A fault-removal intervention also does not prove that an effective repair exists within the allowed policy grammar.

The local runtime should remain local until a separate hosted execution design exists. Mutation endpoints do not have application user authentication. Simulator controls have a separate loopback/capability boundary; that is not multi-user authorization for the main API.

## What remains from the original checklist

The sibling checklist has **117 of 122 items checked**, with five open:

| Task | Plain-English requirement |
|---|---|
| T065 | A genuinely generated repair passes the required source, challenge, promotion and restart evidence gates |
| T088 | The complete sponsor evidence chain, including a versioned regression dataset and automatic Aria evidence |
| T097 | Freeze the actual policy, runtime identities and final/external test definitions |
| T100 | Execute the exported regression, independent-agent transfer and equal-budget selector comparison |
| T102 | Run the final eight-case × three-repeat × three-arm audit: 72 episodes |

These five are large outcome gates. **117/122 is not a meaningful estimate that the product is 96% finished.** Implementation breadth is high; the key improvement and transfer evidence is still missing.

## Documentation that needs reconciliation

`CONTINUE_HERE.md`, the Claude handoff, the checklist header, `sponsor-results.md`, `limitations.md`, `setup.md`, and `submission-checklist.md` contain old statements alongside later corrections. Examples include Aria deferred, repository private, repair/challenge never exercised, V4-only defaults, and uncommitted Claude work.

Retain historical experiment records, but replace present-tense status summaries with a single dated status page. Do not erase failed runs or retroactively reinterpret old source configurations. This report is the baseline for the next plan; it does not mark any outstanding experimental task complete.
