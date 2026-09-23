# Phase 3 results — September 20, 2026

**The new search and completion-study features work, but a useful generated repair is still unproven.** We ran the declared experiments, inspected the actual requests and simulator state, checked the dashboard, and preserved the failed and incomplete outcomes. No policy was accepted or activated.

The work followed [the original protocol](PHASE3_EXPERIMENT.md) and [one predeclared alternate-model follow-up](PHASE3_FOLLOWUP.md). Progress is in [PHASE3_TASKS.md](PHASE3_TASKS.md). These experiments continue the same $1,000 ceiling as Phase 2.

## What changed

- Autonomous search now records a normalized fault-schedule identity. Changing only the seed or order of primitives does not buy another trial of the same schedule. Duplicate suggestions consume their selection slot, retain the original model response, and get no replacement Actor run. The existing invalid-output fallback remains explicitly labeled; it is also subject to duplicate detection.
- A separate completion study can test recovery from truthful unfinished work. It saves its plan before dispatch, requires fresh controls and paired comparisons, and freezes a qualifying candidate before validation. It retains invalid proposals, duplicate proposals, failed trials and interruptions. It cannot activate a policy or call the ordinary promotion gate.
- The dashboard separates requested search schedules from executed trials, and completion studies from ordinary invariant repair. It links original proposals and reports, distinguishes completed experiments from completed tasks, and explains a stop caused by an untriggered fault.
- Added an explicit completion-study CLI and saved development-recording export. Startup, viewing and status queries remain provider-free.

Actor prompt/model, business tools, simulator, C1–C8 checks, policy language and episode limits did not change. The added completion-study provenance value does not relax safety scoring.

## A: autonomous search

Campaign `campaign-7567578d3ed44d9880b3578672ce3725` ended **NO_CHANGE**.

Eight Explorer selections produced eight distinct schedules; there were no duplicates or invalid proposals in this live run. Six of the eight discovery faults actually triggered. Two remained unreachable. This is better schedule diversity than the preceding run's repeated recipe, but it does not establish broad fault coverage or statistical superiority. Duplicate rejection was verified offline, including replay of the earlier saved selections: six selected and two skipped without model calls.

Discovery produced five completed tasks, two safe unresolved tasks and one C6 evidence-citation violation. The violation cited `evidence-6c1b72…` instead of the delivered `evidence-6a6b72…`. Both business effects had succeeded, but the original report was correctly rejected. Three fresh reproduction trials all completed without that error. The source therefore reproduced **0/3**, and no diagnosis, generated safety repair, challenge or promotion was admitted.

Including reproduction: **11 episodes, eight completed tasks, two safe unresolved, one violation; nine of eleven scheduled faults triggered; 61 model requests**. All eleven Weave traces were verified, including readback-only synchronization of the three saved reproduction traces. No Actor trial was rerun for synchronization.

## B: generated completion recovery

Campaign `campaign-3f20fcd4d4b14566a6203d9c110e744c`; study `completion-study-be77b3ad95e74968b8394e136e825a3d`. Actor and Mechanic: DeepSeek V3.1. Result: **NO_CHANGE**.

| Stage | Baseline task completions | Candidate task completions | Result |
|---|---:|---:|---|
| Healthy controls | 3/3 | Not run | Healthy task works in these controls |
| Two transient notification failures | 0/3 | Not run | Truthful unfinished task reproduced |
| First generated candidate, fresh source pairs | 0/3 | 0/3 | No improvement |
| Second generated candidate, fresh source pairs | 0/3 | 0/3 | No improvement |
| Further seven-condition validation | Not run | Not run | Neither candidate qualified |

Both model-generated rules waited and read notification status. Neither retried the original write. The actual notification requests had been rejected before acceptance, so waiting could not make a notification appear. The second proposal received all twelve permitted prior verified episodes and the first proposal's zero-completion assessment, yet described the earlier rule as showing potential. That inaccurate explanation is preserved as model output, not accepted as evidence.

Manual inspection confirmed that the interpreter performed those rules as written. Each failed-source episode had zero notification effects; healthy controls had one. The original reports stayed truthful and unchanged. There was no engine or provider failure.

**18 episodes, 18 verified traces, 129 model requests (127 Actor and two Mechanic).** All 15 scheduled fault trials triggered. Three tasks completed and fifteen stayed safely unfinished. Both policies remain rejected; all 42 validation slots were left unattempted. No generated retry or candidate lost-response behavior was tested live because no candidate reached validation.

## B2: alternative Mechanic was configured but never called

Campaign `campaign-892eee83577a409b82e02deaf73a1a9e`; study `completion-study-52a2c10f8944457bb2a8627452fdc584`. Result: **INCOMPLETE**.

The sole declared change was V4 Pro-0813 for the Mechanic, including its matching provider settings and prices. Actor and runtime remained unchanged. Two source and two healthy controls completed normally. On the fifth trial, the Actor upgraded the order, then read notification status five times without ever calling `send_confirmation`. It truthfully reported UNKNOWN / SAFE_UNRESOLVED and passed C1–C8, but the notification fault was never reached.

The study stopped under the predeclared eligibility rule and did not replace the trial. **No V4 Mechanic request occurred, so this run tells us nothing about V4's ability to generate a repair.** This was an untriggered fault, not a provider or engine failure. The dashboard displays that distinction alongside the original saved generic stop reason.

Five episodes and 33 Actor requests were retained. Four traces had been verified when the decision stopped; later readback-only synchronization verified the fifth. The saved study's original evidence map still says four of five, while the campaign evidence inventory now has all five. Synchronization did not resume the experiment or change its decision. The original record, two completed tasks and three safe unresolved tasks remain intact.

## Manual verification and preservation

The review inspected original model answers, delivered observations, attempted-write journals, simulator databases and final snapshots. B's 18 final model reports exactly match the stored reports; notification effects agree between the independent world databases and saved snapshots. B2's last original action history confirms the missing first notification attempt. A's citation mismatch and all three non-reproductions were inspected directly. Public and private evidence remained separate.

Actual dashboard checks covered search schedules, completion groupings, original proposal links, episode selection, C1–C8 findings, Weave links, campaign switching and reload. Three misleading explanation cases and a real duplicate-panel polling defect were corrected. An independent review checked proposal-input isolation, accounting, stop conditions, unchanged pointers and source identity.

Checks passed: **519 backend tests, 100 frontend tests, production build and three browser fixtures**. The optional automated actual-server execution smoke was skipped; the actual application was checked manually and the paid studies used the real backend and HTTP simulator.

An unchanged-source/settings restart preserved **all 30,812 then-current records, events, pointers and call ledgers** exactly. Readiness reported zero provider calls; dashboard reopening did not change paid-call counts. The pre-phase **29,485 records, 12,369 events and 34 policy pointers** remain unchanged. All campaign active policies remain baseline. Runtime archives, consistent database backups, complete recordings and reconciliations are retained locally under `artifacts/phase3-2026-09-20/` (ignored by Git).

Runtime hash: `155a436c5651707568348ed0a91d5afb5a12b2df1dc9c6b1e20e5fc452f22adb`. A/B configuration: `713b0c7f128cb5204f4cd7e66ff59a3e45c14b60fc59f5f6f0b02aeda5ed0341`. B2 configuration: `2a7fe11fe2631bbbd9e1fdfb3c634863085c4eb2c131daa6217f2799e801621a`. All 173 frozen source files remained identical throughout execution.

## Cost and limits

| Experiment | Episodes | Model requests | Conservative charge bound |
|---|---:|---:|---:|
| A | 11 | 61 | $1.50642 |
| B | 18 | 129 | $2.69610 |
| B2 | 5 | 33 | $0.68970 |
| Phase 3 total | 34 | 223 | **$4.89222** |

All 34 traces are now remotely verified. The 223 requests comprise 213 Actor, eight Explorer and two V3.1 Mechanic requests. Recorded tokens: 810,304 input and 12,716 output, with zero unknown-token requests. Known-token price estimate: **$0.52858505**. Actual billed dollars are unavailable for all requests; a token-price estimate and a conservative admission charge are not an invoice.

Across Phase 2 and Phase 3, conservative charges are **$23.81478**, leaving **$976.18522** of the same $1,000 ceiling. The combined known-token estimate is $2.30454455. No paid overages or deployment were enabled. Aria stayed off.

The mixed episode totals are not an accuracy benchmark: they combine adaptive discovery, reproduction, controls and candidate comparisons. The 29 scheduled faults include 26 triggered and three untriggered cases. Original measured gates T065, T088, T097, T100 and T102 remain open. No accepted-policy restart reuse, protected final audit, accepted-policy transfer or positive completion validation is claimed.

## Best next step

Make the Actor's task progress explicit before spending more on repair search: distinguish an operation never attempted, a write rejected before acceptance, and an accepted operation still pending. The current Actor receives all observations but not a concise attempted-write journal in its turn context. Its repeated status reads of an operation it never started are now directly observed. A bounded future engineering comparison should expose only those already-public attempt facts, keep both arms' tools and checks unchanged, and measure healthy completion plus the fixed notification cases in fresh worlds. Preserve the current source as the control.

After that foundation is measured, revisit generated recovery with a prospectively declared experiment. The alternate Mechanic has not yet been evaluated here. Do not claim a complete self-improving agent product until a generated rule has earned the relevant live evidence.
