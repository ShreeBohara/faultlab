# FaultLab — continuation memory

Updated September 23, 2026 after Phase 19 (the Phase 18 clock drift diagnosed and fixed, $0). Read `AGENTS.md` first.

## Start here

1. `memory/README.md` — reading order and handoff index.
2. `memory/projects/faultlab.md` — product, history, implementation map and current truth.
3. `memory/context/next-phase.md` — the recommended next work and verification requirements.
4. `memory/context/runtime-and-evidence.md` — services, exact saved evidence and budget.
5. `memory/context/pitfalls-and-decisions.md` — errors already investigated; avoid repeating them.
6. `docs/part2/PHASE15_RESULTS.md`, `PHASE14_RESULTS.md` and `PHASE13_RESULTS.md`, then `PHASE12_RESULTS.md` and `PHASE11_RESULTS.md` — the newest measured results; then `PHASE10_RESULTS.md`, `PHASE9_RESULTS.md`, `PHASE8_RESULTS.md`, `PHASE7_RESULTS.md`, `PHASE6_RESULTS.md`, `PHASE5_RESULTS.md`, `PHASE4_RESULTS.md` (read its Corrections section) and `PHASE3_RESULTS.md`.

`memory/START_CLAUDE.md` contains the short continuation prompt. These project files are the portable memory; no prior Codex conversation is required. Recheck volatile state before execution.

## Current truth

- One supported task: upgrade a synthetic order, then send one truthful synthetic confirmation.
- Test services, fault injection, fixed scoring, evidence, replay and the repair machinery exist.
- **No generated policy has been accepted.** As of Phase 9 one generated policy has **qualified on the source case** (3 of 3 completions, 0 baseline completions, 0 violations) — the only one in the project's history — and then failed the frozen validation batch on a single episode. Nothing was promoted.
- Phase 3 is closed: A NO_CHANGE, B NO_CHANGE, B2 INCOMPLETE. Do not resume or replace those trials.
- Phase 4 is closed: two declared Actor-context comparisons, 120 live episodes, 120/120 verified traces, **both REGRESSION**. Nothing was adopted and `faultlab-actor-context/v1` remains the default context everywhere.
- Phase 4's finding: telling the Actor the truth about its own attempted writes helped it choose actions a little (1/3 versus 0/3 completions on `notification-3`, fewer wasted status reads) and reliably broke one report — it wrote `NOT_STARTED` where the contract requires `NOT_REQUIRED`, turning a clean `CORRECTLY_REJECTED` into a C5 violation in 5 of 6 changed-arm trials. The predeclared regression guard caught it.
- The Phase 3 recommendation is therefore answered and rejected as specified. The information gap was real but it was not the binding constraint; the binding constraint is the agent's decision about whether to resend, which is the Mechanic's job.
- Phase 5 is closed: the generated-recovery experiment Phase 3 B2 never reached has now run. Both the V4-Pro-0813 Mechanic and a matched V3.1 control were asked twice each. **0 of 4 proposals contained the one step that fixes the task**, and both second proposals were byte-identical duplicates whose explanations claimed novelty. Both studies ended NO_CHANGE.
- The repair is available: one `retry_original_request` rule at `after_notification_response` is legal and is proven live by the handwritten reference actor, 9/9. V3.1 even described that repair in prose while emitting a policy without it.
- Phase 6 tested the leading hypothesis and **refuted it**. A $0.28 non-scoring probe asked both models directly: 6 of 8 answers said replaying a dispatched write is PERMITTED and quoted the contract; none said forbidden. Clarifying the brief then changed zero proposals. Across Phases 5 and 6 the count is **0 of 6 proposals containing the step**.
- Phase 7 probed twice more and killed both remaining explanations. **0 of 4** responses could state the notification operation was never accepted, though all four quoted `TRANSIENT_UNAVAILABLE`; one answered that the evidence "contains no failing episodes" because every C1–C8 check passed. Handed the diagnosis outright, **0 of 4** emitted the step. The declared Phase 7 intervention was **dropped, not run**, because the probe invalidated its premise — recorded openly in `PHASE7_RESULTS.md`.
- **Phase 8 is the first phase where the read-out moved.** Binding the adjudicated per-episode outcome into `summarize_evidence` — presentation only; the same verdict was already supplied in grouped `observed_outcomes` — took the count from 0 of 6 to **2 of 4**. The V4 candidate completed the source case live in 2 of 3 trials: `policy_steps=4`, two `TRANSIENT_UNAVAILABLE` attempts, two `UNKNOWN` reads, then the policy's replay returning **SUCCEEDED** at tick 8. First generated policy ever to complete it.
- **It still did not qualify and nothing was accepted.** `assess_pairs` wants 3 of 3; the third episode failed C6, and an independent **baseline** episode in the same batch failed C5 and C6. Read the result at its true size: 8A's two proposals are the **same byte-identical policy**, so V4 produced one distinct policy, and the V3.1 control repeated its Phase 5 output byte for byte. Read `memory/context/next-phase.md`.
- **Phase 9 replicated Phase 8 properly and it did not hold.** A paired, interleaved, concurrent-control run of 32 studies gave **T 3 of 14 versus C 1 of 11, Fisher p = 0.604 — not significant**. The control arm produced the step too. **Phase 8's causal claim is withdrawn**; the `task_outcome` presentation is kept because it is harmless, not because it works. The design had ~1.00 power against a large effect, so a large effect is ruled out; an effect of 30–40% is not.
- **Phase 9's real result is elsewhere.** Study T15's candidate is the first ever to pass `assess_pairs` (`SOURCE_QUALIFIED`, L 3/3, B0 0/3). In validation it beat the baseline on four cases and regressed on none, then was correctly rejected for one violation on `notification-18` — where **the Actor hallucinated an evidence ID** (`…a025extremely-9372`, 12 of 13 citations real). The baseline failed the same case independently.
- **The binding constraint is now measured and it is the Actor, not the Mechanic.** Candidate episodes violate C5/C6 at **16–28%**; baseline episodes at ~3%. The step itself works: all four step-containing candidates completed the source case at least 2 of 3.
- **Half of every study is wasted**: 16 of 32 Phase 9 studies burned their second proposal slot on a byte-identical policy.
- **Phase 10 changed what this project thinks it has been measuring.** T15's policy was replayed through the frozen validation batch 26 times: **0 of 13 scored replays were accepted** (Wilson 95% [0.000, 0.228]). The gate accepts a *provably working* repair essentially never.
- **The cause is the Actor, not the policy.** Candidate-arm violations 26/414 (6.3%) against baseline 21/414 (5.1%) — about 1.2 points of excess. Phase 9's 16–28% figure was source-case only and did not generalise. **62% of violating episodes cite a fabricated evidence ID.**
- **The mechanism is transcription, not reasoning.** The Actor copies 32-character hex evidence IDs and corrupts one about **3.4%** of the time (measured on 1,284 reports). The token **"extremely" has been spliced into a hex ID four separate times**; other IDs lose characters. `notification-18` cites 13–14 of 15 observations and is the worst case in **both** arms.
- **The honest restatement:** FaultLab has generated a policy that completes the task, and its gate cannot certify one, because the gate's unit of evidence is an Actor-transcribed identifier corrupted ~6% of episodes. **Do not loosen the gate** — fix the evidence it judges.
- **A second expensive limitation:** one transient provider timeout makes an episode `LAB_ERROR`, the evidence gateway refuses it, and the whole 42-episode batch aborts. 13 of 26 Phase 10 attempts died that way; only 8 of 26 gave a clean quality verdict.
- **Phase 11 removed the transcription and the failure went with it.** `faultlab-actor-context/v4-indexed-evidence` shows the Actor `obs-1 … obs-n` instead of 32-hex identifiers; cited labels are decoded exactly, with unmatched tokens passed through verbatim so they still fail C6. **`checks.py` was never opened and `scorer_hash` is unchanged.**
- **370 episodes under v4: zero fabricated identifiers** (v1 baseline 3.43%), the ≥12-citation regime went 30% → 0 of 14, and the **C1–C8 violation rate went 6% → 0%**.
- **Quality rejections 8 of 13 → 0 of 7 (p = 0.015).** Every Phase 11 non-pass was batch fragility, not policy quality. The **declared primary read-out is 2 of 6, p = 0.088 — not significant**; the pre-declared pooled figure is 3 of 7, p = 0.031. Quote both, never one alone.
- **The Phase 4 regression guard passes**: no case lost its target outcome, none gained a violation, fault triggering unchanged (97.5% → 97.4%), Actor behaviour unchanged. `notification-18` went 66% → 92%.
- **A pre-registered concern came out backwards**: judges predicted cheap labels would cause blanket citing and erode C6. Breadth *fell* (0.887 → 0.735) — the Actor became more selective, which is the harder direction.
- **The binding constraint has moved again, to batch fragility.** Two measured causes: one `LAB_ERROR` aborts a whole 42-episode batch via the evidence gateway, and one untriggered fault (97.4% trigger rate over ~23 fault-bearing episodes → ~46% of batches) makes it `INCOMPLETE`. Separate changes; neither is a gate change.
- **Phase 12 built a bounded blind retry for transient Actor transport failures and could not measure it.** 28 attempts, 0 scored, $8.15, aborted at the cap — **W&B Weave ingestion degraded from a 0.9% to a 31% per-episode failure rate**, so no 42-episode batch could ever verify. **This was not a code regression**: 0 `LAB_ERROR` episodes in 91, 0 new provider failures, the retry never fired.
- **Phase 13 replicated Phase 11's acceptance at roughly double the scored n. 5 of 13 scored replays returned `OBSERVED_IMPROVEMENT`** (Wilson [0.177, 0.645]) against Phase 10's 0 of 13 — Fisher two-sided **p = 0.039**, intervals disjoint. 30 attempts, 849 episodes, $91.42 plus a $4.70 health probe. **Phase 11, not Phase 13, was the first phase to get a replay accepted** (2 of 6). What Phase 13 adds is that the significant figure is now the *single* declared read-out: Phase 11's significance depended on which of two pre-declared figures you quoted (2 of 6, p = 0.088 vs pooled 3 of 7, p = 0.031), and this one does not.
- **Quote the shortfall with it.** The declared target was **20 scored** and the run reached **13** at the 30-attempt cap. The read-out was not re-declared after the fact. At 13 scored the design cannot separate 0.38 from 0.25 or 0.60.
- **Zero quality rejections again: 8 `INCOMPLETE`, 0 `NO_CHANGE`.** Pooled with Phase 11 that is **0 quality rejections in 20 scored replays**, against Phase 10's 8 of 13. The citation fix's effect holds.
- **Phase 12's declared objective is unmet.** Yield was 13/30 = **0.433** against an all-prior 20/39 = 0.513 and a predicted ~0.6; Fisher **p = 0.63**. Recorded as a null, not reframed.
- **But Phase 12's retry is now measured and it works.** Actor transport failures: Phase 10 had 10 and **0 of 10** episodes survived; Phase 13 had 5, retried 4, and **4 of 4 survived** — Fisher **p = 0.0037**, Wilson intervals disjoint. **This is a historical, not concurrent, control** — say so whenever quoting it.
- **Two of my own mid-session claims were wrong and are corrected in `PHASE13_RESULTS.md`.** (1) "The retry never fired — 0 events" — it fired 4 times; my query searched `records` for events that live in the separate **`events` table**. (2) "The unscored attempts died in the runner's HTTP polling" — they died **inside episode execution**; `error_type` is written by `completion_study._execute`'s own handler.
- **The 5th transport failure exposed a real bug, now fixed.** It hit on the **8th of 8** actor turns: `meter.model_call()` increments `actor_calls` *before* the guard reads it, so `8 < 8` was false and **the retry was structurally unreachable on the final turn** — the turn carrying the report. The same design also cost an episode a whole reasoning turn (7 instead of 8) on any retry, which the old test was pinning. Fixed by `EpisodeMeter.transport_retry()`: charges dollars and `model_calls`, spends **no actor turn**, returns False rather than raising. The `actor_calls` contract bound (`le=8`) is unchanged and still bounds generations. **Built, tested, unmeasured.**
- **The dominant failure channel is somewhere nobody had looked, and it is not the Actor or Weave.** Of 17 unscored Phase 13 attempts: **`ReadError` 11 (37% of all attempts)**, `WaitingEvidence` 5, `EvidenceDenied` 1. `WorldClient.control()` — the path for `create`, `advance`, `stop`, `snapshot`, `faults` — had **no transport handling at all**, while the business-tool path below it has always converted transport errors safely. One dropped localhost read aborted a 42-episode batch.
- **That is instrumented, not fixed, on purpose.** `WorldControlError` names the failing operation and subclasses `httpx.TransportError` so every existing classification is unchanged. It **retries nothing**: `advance()` and `create()` are not idempotent, so replaying one whose response was lost could double-advance a world. Which of the five operations fails is **still unknown**; the instrumentation ships unused.
- **The evidence channel was healthy in Phase 13**: 5 `RETRYABLE_ERROR` of 848 episodes (0.6%, all `TRANSPORT`), mapping one-to-one onto the 5 `WaitingEvidence` deaths. Phase 12's degradation had genuinely cleared.
- **Phase 14 answered Phase 13's open question for $0 and the answer is `create()`** — `POST /control/worlds`. 16 agents, four angles, each adversarially verified by three lenses; no paid run. `execute_slots` wraps `runner.run` in no try, `runner.run` has no finally and two blanket `except Exception`, and in the unprotected window `create()` is the only HTTP call that exists. All 14 `ReadError` studies store-wide leave exactly one slot `INTERRUPTED`; all 56 evidence-channel studies leave zero.
- **The failing request never reached the simulator.** Scanning all 3,730 world files for the 14 episode_ids gives zero hits, and zero orphans exist with a Phase 13 mtime; independently, a server-side counter gave 900 trials → 884 client successes → 884 server-side, difference zero. A retry therefore cannot double-create.
- **Why it fails is now FOUND and proven in uvicorn's source.** uvicorn arms its keep-alive timer in `on_response_complete` — when it finishes **writing** a response (`h11_impl.py:331`) — so its deadline always falls before the client's, which starts when the client finishes **reading**. The handler then calls `transport.close()` without draining the socket (`h11_impl.py:372`), and on macOS closing a socket holding unread bytes emits **RST, not FIN**. A `create` request that lands in the receive buffer just before the deadline is discarded before the ASGI app runs — which is exactly why no world file ever existed — and the client sees `httpx.ReadError`.
- **Every observation has a cause now**: threshold at exactly 5.000s = uvicorn's default; app never ran = discarded in the transport; always `ReadError` and never `RemoteProtocolError` (0 of each other class across 138 studies) = RST not clean FIN; the hazard **decays** from 5.0s = the event loop's scheduling latency between deadline and close.
- **There is no upper edge, and my asking for one was a false premise.** Hazard: [5.0,5.5) 11/155, [5.5,6.0) 2/67, [6.0,7.0) 0/76, [7.0,∞) 0/109 — a ~0.4–0.5s decay, under which zero above 6.0s has **P = 0.68**. Exposure is not homogeneous (gap is driven by the preceding episode's telemetry size), and stratifying moves the "upper edge" from p = 0.0009 to p = 0.02–0.21. The **lower** edge survives every stratification (p < 5e-6).
- **Best predictor is a straddle**: `A < 5.0 <= gap` (A = time to evidence retrieval) gives 10/110 vs 1/761, Fisher **p = 7.0e-09**, beating the band by 2.9 logL at equal parameters. 87 of the 93 exposures above 6.0s are not in the at-risk class at all.
- **Refuted, do not re-propose**: TIME_WAIT/ephemeral-port collision (72/72 served), teardown racing accept (216/216 served), and a *fresh* connection being reset (888 trials, 0 resets). The victim is always a **reused** connection the server has just closed.
- **The real fix is connection lifetime, not the retry.** `WorldClient` now sets `httpx.Limits(keepalive_expiry=2.0)` against the simulator's 5s, so the **client** always closes first and the server never closes a socket with a request in it. Verified deterministically: at 4.9s idle the old client REUSED the connection (the dangerous state), the new one dials fresh from 2.5s on. `scripts/start-simulator.sh` also passes `--timeout-keep-alive 75` as defence in depth. This changes only TCP connection lifetime — no handler, response, fixture, fault schedule or referee input.
- **The bounded `create()` retry stays as a backstop** — 3 attempts, jittered, transport only, `HTTPStatusError` still fails fast, recorded via the free-form `episode_started` payload (never a model field; `StrictModel` is `extra='forbid'`). Measured: **551 of 551** induced `ReadError`s recovered on attempt 2 across two independent harnesses; zero backoff recovers too, so there is no poisoned pool.
- **Two real defects in my first retry, found by review and fixed**: it had **no jitter** (a fixed ladder resonates with a periodic cause — measured 12 failures of 14 unjittered vs 1 of 14 jittered) and **`CREATE_BACKOFF` was indexed without a clamp** while being one shorter than `CREATE_ATTEMPTS`, so raising the attempt count raised `IndexError`. Note for tuning: the ladder's **span** buys protection against a persistent cause, not the attempt count.
- **Rejected a "strictly better" review recommendation**: marking a lost slot and continuing. `assess_pairs` requires all 42 slots (`len(rows)==len(expected)`), so it returns `INCOMPLETE` anyway while paying for ~21 more episodes. Same correction as T195 in Phase 12.
- **Safe for `create()` and nowhere else.** Nothing anywhere resolves a world from an episode_id (verified across simulator, lab, referee, frontend, CLI), and no untriggered-fault count scans the worlds directory, so the fatal-untriggered-fault rule is untouched. Measured on a repeat: `create` → two distinct worlds; **non-observer `advance` → tick 2 then 4, double-applied**, which can flip `fault_triggered` → `valid_trial` → whether a pair qualifies. An anti-regression test asserts the other four operations are called exactly once.
- **Correction to Phase 13's write-up:** the **observer** `advance` *is* idempotent — `clock.advance` latches `horizon_done` atomically with the tick (measured: retry returns 409 `INVALID_OBSERVER_ADVANCE`, tick unchanged). Only the non-observer `advance` is unsafe.
- **Correction: the protected teardown calls did NOT fail zero times.** The 3 `SIMULATOR_OR_SCORER_ERROR` episodes **each killed a study** — they are the single `LAB_ERROR` slot in 3 of the 20 `EvidenceDenied` studies. A `create`-only retry leaves that route open; it is deliberately left for a separate, measured change.
- **Correction: the "three independent absences" in Phase 13 are one fact.** `events.episode_id` has a foreign key to `episode_registry`, which is written only by `put_record` for `kind=='episodes'`. Still decisive, but one strand.
- Phase 14 changed `business_tools.py`, so `adapter_hash`/`runtime_hash`/`configuration_hash` moved. `algorithm_hash` (only `backend/app/lab` + `backend/app/referee`) is unchanged, which shows no **acceptance logic** moved — it does not make configurations identical.
- **Phase 15 reached the declared read-out for the first time in the project's history: 20 scored replays, 9 accepted, Fisher p = 0.005 vs Phase 10's 0 of 13.** Pre-declared threshold was >=7 of 20; met. Against Phase 13's 5 of 13 (a reference, not adjudicating) p = 1.00 — a clean replication. 28 attempts, 914 episodes, **$97.33**. Manifest and store reconcile with **0 discrepancies**.
- **The headline is NOT mainly measuring the gate, and the protocol said so in advance.** Since Phase 11 removed citation corruption, a pass largely means *all 36 fault-bearing episodes fired*. Untriggered rate: Phase 10 1.28%, Phase 13 2.75%, **Phase 15 2.02%** [1.27%, 3.22%] — predicting a 0.479 pass rate against 0.450 observed. **Always quote the untriggered rate beside the headline.**
- **The number that isolates the gate, and the cleanest result the project has produced: of scored replays with ZERO invalid trials, 9 of 10 were accepted; of those with an invalid trial, 0 of 10.** When every fault triggers, the gate certifies this repair 9 times in 10. When one does not, never. Total separation.
- **Full decomposition of 28 attempts**: 9 accepted (32%), 1 quality-rejected on a clean batch (4%), 10 `INCOMPLETE` from an untriggered fault (36%), 8 lost to the evidence channel (29%), **0 lost to the lab control path**.
- **S2 — the Phase 14 fix is confirmed: 0 create-caused aborts of 28 attempts** against Phase 13's 11 of 30 (Fisher **p = 0.000334**), and 0 of 914 episodes against 11 of 849 (**p = 0.000312**). Not one `ReadError`; `control_operation` was never written because no control call failed. The 37% channel is closed.
- **S1 — quality rejection is near-eliminated but NO LONGER ZERO.** Phase 15 unpooled **1 `NO_CHANGE` of 20** (reason: `Expected outcome regressed within a validation case`, on a clean batch), vs Phase 10's 8 of 13, p = 0.000529; pooled 11+13+15 = 1 of 40, p = 0.0000118. **Do not write "zero quality rejections" again without this footnote.**
- **S3 — yield 0.714** (20 of 28), inside the declared 0.68–0.74, vs Phase 13's 0.433. Phase 12's original objective is met two phases after it was set, by fixing a channel Phase 12 never identified.
- **The evidence channel is now the ONLY remaining loss channel**: 8 of 28 attempts (29%), 7 `WaitingEvidence` + 1 `EvidenceDenied`. Nothing in Phases 13–15 addressed it.
- **Declared contamination check**: 7 of 20 scored batches (35%) contained an `actor_transport_retry` event, higher than the ~20% the protocol estimated. Reported as measured.
- **A four-lens pre-run review returned RUN_WITH_CHANGES on every lens and was worth it.** It caught a **false integrity claim in my own declaration** (`algorithm_hash` is CHANGED, not unchanged — `assess_pairs` lives in a file Phases 13–14 edited; its own text was not edited, hash `783e8e58…` recorded, but no byte-for-byte proof against Phase 13 exists because the file is untracked and that phase took no freeze), an undeclared change to episode execution, a read-out dominated by an undeclared nuisance, an undeclared stronger figure, no power calculation, an optimistic yield (0.8 vs the correct 0.68–0.74), a circuit breaker at 4 that would have aborted Phase 13 at attempt 22, and **two latent runner defects that silently deleted verdicts the gate had already reached** — both biased toward discarding *scorable* replays. All fixed before spending.
- **Before any paid replay run, check ingestion health first**: `./.venv/bin/python scripts/experiments/check_ingestion_health.py` (read-only, $0). It exits non-zero and prints the implied probability a 42-episode batch completes. The runner also now aborts after 4 consecutive attempts with no validation assessment.
- Phase 6 also measured the source gap honestly for the first time: the baseline completes it **2 of 45** valid triggered episodes (4.4%), so any three-trial gate fails ~13% of the time by chance. Study 6B stopped exactly that way. **Correction made in Phase 8:** adding trials does not help, because against an absolute zero-completion gate more trials can only make a stop more likely. The only honest prospective mitigation is more independent study runs, capped and declared in advance and only after a stop that produced no proposal. Never loosen a threshold.
- **Known, unresolved:** an intermittent full-suite test failure (~1 in 8 runs, in the untriggered-control path, pre-existing) was investigated in Phase 10 and not explained. Do not report the suite as unconditionally green.
- Phase 4's work was adversarially reviewed after the fact and three real code defects plus four wrong numbers were found and fixed. No Phase 4 conclusion changed; the corrections are listed in `PHASE4_RESULTS.md`.
- Latest verification: **692 backend tests** (Phase 19, 2026-09-23); 124 frontend tests, production build and three browser fixtures as last recorded (not re-run since; the frontend is unchanged); actual dashboard, per-turn request reconstruction, original reports, simulator effects, Weave and restart checked manually.
- Main checklist: sibling `../FaultLab_Specs/specs/001-faultlab-loop/tasks.md`. T065/T088/T097/T100/T102 remain open; Phases 4 through 15 closed none of them. Checked investigation tasks do not mean the learned-repair goal passed.

## READ THIS FIRST — Phase 16 (2026-09-22) corrected the handoff that preceded it

An earlier section here recommended "run full completion studies until a policy is ACCEPTED,
$15–50". **A read-only audit, and two adversarial review rounds, showed that plan could not
work.** See `docs/part2/PHASE16_RESULTS.md`.

- **Completion studies cannot write ACCEPTED** (by design and by spec). The target is now a
  separately labelled **certified completion repair**:
  - `OBSERVED_IMPROVEMENT` under the unchanged `assess_pairs`, **plus**
  - `L − B0 ≥ 2` completions on a validation case other than `notification-2` and `healthy`.
- **All 40 full studies ran on the v1 Actor context.** The default is still v1, so pass v4
  explicitly.
- **The step rate:**
  - 5 of 31 first proposals contained the step;
  - the second slot is a duplicate 20 of 25 times (temperature 0);
  - 15 of the "16 of 100" were valid; the 16th has a corrupted key.
- **The source gate:** 1 of 5 step candidates qualified. **3 of the 4 failures were C6
  citation errors, and the 4th was an untriggered trial.** Unmeasured under v4.
- **Untriggered faults:** all 73 are the same Actor lapse (it polls a confirmation it never
  sent, then gives up). The documented 2.02% should be 2.64% per fault-bearing episode.
- **`EvidenceDenied`** is always a lab-error episode (21 of 21).
- **Phase 16 changed only:**
  - an in-study evidence re-read (`completion_study.verified_evidence`, `EvidenceGateway.retry`,
    `WeaveWorker.ensure_running`);
  - the health check;
  - new scripts: `gate_freeze.py`, `expected_configuration.py`, `run_full_loop.py`,
    `phase17_readouts.py`.
- **Phase 16 verified:**
  - `assess_pairs` is text- and AST-identical (`783e8e58…`);
  - `scorer_hash`, `contract_hash`, `source_hash` and `actor_prompt_hash` are unchanged;
  - `algorithm_hash` is `8d92e0c5…` and `runtime_hash` is `485c5e12…`;
  - the expected `configuration_hash` is `c4169ee4…`, cross-checked against Phase 15's
    stored configuration.
- **Tests:** 594 before; 53 new; **647 passed after** all Phase 16 changes. The intermittent `[untriggered]` failure is still unexplained.
- **Phase 17 ran on 2026-09-23 and CERTIFIED a repair on attempt 9 of 9 ($24.29 bound).**
  - The certified policy is new (`dd62c857…`, not T15's). It repaired the source case and
    `notification-3` (0 → 3 each), with zero candidate violations, zero untriggered faults
    and no regression.
  - Attempt 4's repair was rejected for turning `CORRECTLY_REJECTED` into `SAFE_UNRESOLVED`:
    it deferred without waiting and re-reading.
  - S1: 3 of 7 first proposals contained the step. S2: 2 of 4 step candidates qualified; the
    other 2 gated the retry on PENDING and could never fire.
  - The evidence re-read was never needed (0 of 192 reads failed).
  - It is **not ACCEPTED**, and Phase 17 is closed. See `docs/part2/PHASE17_RESULTS.md`.
- **Phase 18 ran on 2026-09-23: a held-out check of `dd62c857…`. Verdict HARM, final ($4.22 bound).**
  - The run was one attempt on the private promotion partition: 6 unseen cases, 18 pairs,
    all valid, with 0 untriggered faults.
  - **1 candidate episode failed C5, C6 and C8** (delayed-confirmation case). The baseline
    had 0 failures.
  - The policy acted in 10 of 18 candidate trials; the failure was its only
    notification-side action.
  - The refusal case held (3 of 3 correctly rejected). On transient upgrade failures the
    candidate completed 0 of 3 against 1 of 3 for the baseline (descriptive only).
  - **The post-verdict investigation** ($0, read-only, not declared in advance):
    - the failing report was **true about the world**;
    - the lab's tick ran one ahead of the simulator's, because an automatic same-`call_id`
      re-send after a timeout was never recorded by the world;
    - the cited evidence therefore landed "after" the world's decision tick, and C6 failed.
  - **The same drift:** 4 of 4,791 stored episodes, all C6 violations, **2 of them
    baseline**. It first appeared on September 22 (0 drifts in 1,655 earlier episodes with a
    re-send), and Phase 17 contains none.
  - The verdict stays HARM. Held-out safety for this policy is **unshown**, and the
    partition is spent for it. See `docs/part2/PHASE18_RESULTS.md`.
- **Phase 19 (2026-09-23, $0) diagnosed and fixed the drift.** See `docs/part2/PHASE19_RESULTS.md`.
  - **Mechanism (reproduced):** a lab request that must open a **new connection** is lost
    unsent if the lab's event loop freezes for over 1 s while it connects. httpx raises
    `ConnectTimeout` before writing, but the broker has already counted the tick.
    - Fresh connection: 12 of 12 lost. Otherwise: 0 of 24.
    - Real broker: old code 6 of 6 drift; new code 0 of 6.
  - **Freeze source** (supported, not proven for the four historical cases; the logs lack
    timestamps):
    - an open **dashboard tab** polled `/matrix` and `/experiments` once a second;
    - both parsed every episode and evidence record on the event loop;
    - the idle backend stalled ~0.8 s of every second, at 60% CPU.
  - **Fix:**
    - those endpoints read only their own campaign (0 output differences on all 214
      campaigns);
    - lab requests get `connect=10 s`, with read, write and pool unchanged at 1 s (control:
      3 s);
    - a new read-only `scripts/experiments/check_clock_drift.py` (use `--worlds --since`
      around paid runs).
  - **Measured:** dashboard-on loop latency p50 611 ms → 2.4 ms, p99 1,180 ms → 68 ms.
    Tests: 692 passed.
  - **Unchanged:** `assess_pairs` (`783e8e58…`) and `scorer_hash` (`19de811c…`). Four
    fingerprints moved, all declared. The next expected `configuration_hash` is `0a33aa51…`.
  - **Store-wide:** 4 drifts and 6 **masked** F1 faults. In the masked cases a lab freeze let
    a delayed response be read as success, so the Actor never saw the fault. Among them:
    - Phase 15 replays 1, 5, 12, 21, 24 and 28, and one Phase 13 replay;
    - **no declared read-out of Phases 13, 15 or 17 changed** (replay 5: L completed that
      case 55 of 55 with the fault visible);
    - **Correction:** Phase 18's HARM does NOT hinge on the defect. Rule 3 (`lost_outcome`)
      still fires on stale history (L 2 vs B0 3, where the policy never acted) and on
      transient upgrade failures (L 0 vs B0 1). The defect decided only which rule fired
      first. Rule-3 HARM at n=3 is weak evidence (per-case false alarm ~33% at a 1-in-3
      baseline rate).
  - **Remaining paths**, rare and documented:
    - a freeze longer than 10 s;
    - a simulator started without `--timeout-keep-alive 75`, so always use
      `scripts/start-simulator.sh`;
    - a refused connection;
    - the broker still counting an attempt before it is sent.

- **Phase 20 (2026-09-23, $18.77): development probe of `dd62c857…`, 138 episodes.** See `docs/part2/PHASE20_RESULTS.md`.
  - **Safety:** 0 C1–C8 failures in either arm (0 of 69 each).
  - **Completions kept:** L kept all 33 of 33 that B0 had on short delays, lost upgrade response, stale history and healthy.
  - **Source check `none_found`:** no baseline fails any check 3 of 3, so **the ACCEPTED path has no known source** in the trusted configuration. T065, T097 and T102 are blocked by that absence. This is bounded evidence.
  - **Transient upgrade failures:** P-1 is **floor-limited** (B0 2 of 27, L 0 of 27). A cost cannot be ruled out; it is descriptive only.
  - **Descriptive:** L completed the F2 d5 boundary delay 3 of 3 where B0 completed 0 of 3.
- **Phase 21 (2026-09-23, $22.22): Actor replay probe of the lapse. V5_NOT_ADOPTED.** See `docs/part2/PHASE21_RESULTS.md`.
  - **At the point of lapse (turn 4):** stating "no confirmation requested yet" made the Actor send 3 of 65 times, against 0 of 65 for both C and the placebo. It FAILED.
  - **The lapse is a chance draw on turn 3:** the same prompts now send 83%. It is absorbing once the Actor has polled and read UNKNOWN.
  - **Temperature 0 is not deterministic:** only 36% of repeat pairs are byte-identical.
  - The untriggered channel stays fatal. Phase 25 falls back to 12 v4 replays.

- **Phase 22 (2026-09-23/24, $0): build, two review rounds, freeze, seal.** See `docs/part2/PHASE22_RESULTS.md`.
  - **Held-out check v2** (15 trials per case, Fisher) was built beside the unchanged v1.
  - **v2 was ADOPTED** although its declared criterion is not met literally; the reasons and
    the non-compliance are recorded in the Review log.
  - **heldout-2 was sealed:**
    - the seed sha `470aaac0…` was committed before any draw;
    - manifest `c902f1c9…`, 6 cases;
    - nobody opens the seed or the partition.
  - **Freeze:** `8994e962…`; configuration `2cf63e93…`. `assess_pairs` and `scorer_hash` are
    unchanged.
  - **Tests:** 1,165 passed, 0 failed.
- **Phase 23 (2026-09-24, $77.30): 3 of 30 attempts certified a completion repair (Wilson 95% [0.035, 0.256]).** See `docs/part2/PHASE23_RESULTS.md`.
  - **Three distinct policies:** `711bddb6…` (attempt 2, routed), `5735a918…` and `d4bc993e…`.
  - **Funnel:** the step was in 7 of 26 first proposals and fired 8 of 8. The source gate
    passed 6 of 6. 3 of 4 clean batches were accepted.
  - **Duplicates:** slot 2 repeated slot 1 in 16 studies.
  - **Lab integrity:** 0 drift and 0 masked faults in 613 episodes. The evidence re-read was
    used once, and verified.
  - **Pooled with Phase 17:** 4 of 39.
- **Phase 24 (2026-09-24, $17.12): heldout-2 v2 check of `711bddb6…`. Verdict HARM (`check_failure`), final.** See `docs/part2/PHASE24_RESULTS.md`.
  - **The failure:** 1 of 78 candidate episodes failed C5/C6 on transient upgrade failures.
    The policy acted correctly (read, wait, read, require a receipt), but the Actor reported
    `upgrade_outcome: PENDING` where every observation said `UNKNOWN`.
  - **The baseline had 0 failures,** and the lab was clean (0 drift).
  - **Without rule 1** the attempt would have been INCOMPLETE, and rule 3 fired nowhere.
  - **Otherwise the repair matched or beat B0 on every case.**
  - **Held-out safety is unshown again.** heldout-2 is now spent.
  - **Recurring descriptive pattern:** the repairs never complete transient upgrade failures,
    while B0 sometimes does by re-sending: 0 of 45 against 5 of 45 over Phases 18, 20 and 24.
    Two different policies. It is a development hypothesis, never a held-out finding.

## Authorization and budget carried forward

The user authorized autonomous implementation, manual verification, repeated/broader experiments and subagents. They explicitly authorized W&B Inference/Weave provider calls and the entity `shreetbohara-quinstreet`, with a **shared $1,000 ceiling for Phases 2 onward**. Do not ask them to repeat those approvals for unchanged scope. Routine judgment is expected; communicate simply and keep progress checklists current.

After Phase 24: **$600.65 conservatively charged; $399.35 remaining** (Phase 16 $0; Phase 17 $24.29; Phase 18 $4.22; Phase 19 $0; Phase 20 $18.77; Phase 21 $22.22; Phase 22 $0; Phase 23 $77.30; Phase 24 $17.12). (Phase 14 cost $0; Phase 15 cost $97.33.) (The cost table's rows sum to $243.28 through Phase 12 while its headline said $243.00 — a pre-existing $0.28 discrepancy, the size of one probe; the higher figure is carried.) This is not a new allowance. Actual billed dollars are unavailable. Per-campaign $400 is an allocation inside the shared ceiling, not extra money. Reconcile any later use before new dispatch. No deployment, paid overages or new public push is part of this handoff. Aria remains off.

## Preserve work

- Repository is local `main`, HEAD `cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe`, with substantial **uncommitted and untracked implementation**, now including all Phase 4 source, tests and documents. Preserve it. A fresh GitHub clone alone is insufficient.
- Existing `.env` contains credentials; never print, overwrite, commit or place it in frontend/memory. The saved settings files are non-secret overrides.
- Local `artifacts/` contains the databases, worlds, source freezes and recordings. It is ignored by Git. Preserve it and all negative results.
- Do not weaken C1–C8, repeat until lucky, fabricate promotion, rewrite original reports, or use protected/private truth in model inputs.
- Saved evidence: `artifacts/phase4-2026-09-20/`, `artifacts/phase4-followup-2026-09-20/`, `artifacts/phase5-2026-09-20/`, `artifacts/phase6-2026-09-20/`, `artifacts/phase7-2026-09-20/`, `artifacts/phase8-2026-09-20/`, `artifacts/phase9-2026-09-20/`, `artifacts/phase10-2026-09-21/`, `artifacts/phase11-2026-09-21/`, `artifacts/phase12-2026-09-21/`, `artifacts/phase13-probe/` and `artifacts/phase13-2026-09-21/`. All studies are closed and must not be resumed or re-tuned.
- Every regression bundle saved before Phase 4 no longer validates, because regenerating the contracts changed their frozen digests. That is the integrity check working; do not add a legacy escape hatch.
- Old September 13 handoffs and `docs/part2/CURRENT_STATE.md` are history. The latter is a preserved pre-implementation audit; its old counts are not current state.
- Services were idle and reachable at handoff. Inspect before restarting; never interrupt an active paid run.

## Team and communication

Shree Bohara and Aryan Bhusari, Team Gatekeeper. Building for a second CoreWeave event roughly a month after the original hackathon; no judging brief or exact Part 2 date is confirmed. Both can work full time with coding agents. Explain in simple English, lead with what works and what remains, and do not ask again about settled routine choices.
