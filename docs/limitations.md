# Evidence and limitations

FaultLab implements one scope: upgrade an authorized order to express shipping and record one truthful simulated confirmation. Notifications never send real email. The four ordinary fault primitives preserve the frozen service contract. C1–C8 score actual private effects and the original actor report against delivered public evidence.

Real model execution, campaign trace readback and a 36-trial Llama baseline evaluation are verified; current learning outcomes are in `docs/learning-results.md`. The V3.1 campaign completed 119 episodes and 829 model calls with no provider errors and all 119 episode traces verified, but no diagnosis qualified for repair. These results do not establish learned improvement or independent transfer. Aria setup remains explicitly deferred. All malformed, flaky, untriggered, rejected, interrupted and no-gain attempts remain evidence.

The current default, `deepseek-ai/DeepSeek-V4-Pro-0813`, has passed action, report, Explorer and diagnosis response-format checks with the documented thinking toggle disabled. Its healthy order and final eight-episode learning attempt completed without provider errors and with verified traces. No fixed invariant failed, so live repair, challenge and promotion remain unverified. The earlier default-thinking probe exhausted 4,000 output tokens without final content; disabling thinking produced a valid 240-token diagnosis response. Valid JSON does not establish that a model's diagnosis is correct. See `docs/model-selection.md` for the retained checks and source documentation.

The 2026-09-13 V3.1 repair-loop campaign (`campaign-44085f54a24144b78252d8eea211ebb8`) reached a supported diagnosis, a model-generated policy, a passing source validation and a challenge that found a counterexample, then ended NO_CHANGE. The generated policy narrowed but did not remove the V3.1 actor's failure to submit a final report, and the Mechanic repeated the same policy despite the returned counterexample. No learned policy is accepted. See `docs/learning-results.md`.

The 2026-09-13 split-role campaign (`campaign-aa79023053da470984118fdb1e9d8138`, DeepSeek V3.1 under test, DeepSeek V4-Pro-0813 as Explorer and Mechanic) reached a supported diagnosis on its first source and produced four model-generated candidate policies, all with identical content. Every candidate repaired the original failure in only two of three pairs, or one of three, so none met the fixed 3/3 source-validation requirement and the campaign ended NO_CHANGE without reaching challenge or promotion. The saved episodes locate the remaining limit in the agent under test, not in the policy: with the receipt already delivered by the policy and the confirmation already sent, V3.1 still failed to emit a valid final report in 5 of 12 candidate trials, against an incumbent that completed 0 of 12; at that observed 7-of-12 repair rate a 3/3 batch clears only about one time in five. A second limit is unchanged across both lab models: V3.1 and V4 both placed the honest `defer_unresolved` step only in `before_final_report`, a hook the interpreter reaches only when a report has already been proposed, so the step cannot rescue an agent that never reports. The per-hook invocation boundaries are not among the facts the Mechanic receives. No learned policy is accepted; see `docs/learning-results.md`.

Aria is no longer deferred. An observed W&B automation fires `Trigger ARIA` automatically when a run named
`^faultlab-campaign-.*` reaches FINISHED, verified against W&B's GraphQL API including a byte-exact match
between the stored prompt and the reviewed prompt. Aria's immediate reply is HTTP 202 with a thread id, which
is a dispatch and not evidence of analysis. Completion was confirmed by reading the conversation back from
W&B's agent service, which reports the thread as `completed` with 140 messages and 46 tool calls; the
operator summary was checked against that text. That endpoint is undocumented and is not an allowlisted
evidence host, so it verifies the summary but does not itself constitute recorded evidence, and the capture
remains attributed operator observation rather than independent remote verification. One capture is COMPLETED with an Aria-authored report as
its output URL, and an earlier UNVERIFIED capture is retained rather than removed.

Aria's counts must not be read as audited figures. For the published campaign it described 18 episodes with 13
completed and 3 correctly rejected, while that campaign holds 36 discovery episodes with 28 completed, 6
correctly rejected, 2 violations and zero lab errors; its denominators correspond to the 18 published Weave
links. Where it could be checked against saved records it also agreed, reporting 7/12 completed for the
`campaign-aa790230` candidate, which matches the direct count. Advisory Aria output cannot and did not change
any policy, checker rule, budget or promotion decision.

Aria did surface a real defect in this project's telemetry. Genuine contract violations are traced as
infrastructure failures: for `campaign-44085f54a24144b78252d8eea211ebb8` all 143 episodes have referee lifecycle
COMPLETED with 77 VIOLATION verdicts and zero referee lab errors, yet the `run_episode` traces mark exactly
those 77 as `terminal_status: LAB_ERROR` with `error_category: PROTOTYPE_EXCEPTION`. The span handler in
`backend/app/telemetry/tracing.py` labels any escaping exception LAB_ERROR, while `backend/app/lab/runner.py`
does not treat `ActorReportError` as a lab error. External analysis based on Weave will therefore understate
genuine reporting failures and overstate infrastructure faults. A fix is tracked separately, and traces already
written to Weave cannot be relabelled.

Two operational deviations are recorded rather than hidden. The Finished run for
`campaign-63933675566f49a994eb3e5bb6145434` was published by an operator script invoking the same `AriaBridge`
rather than by the coordinator's end-of-campaign hook, and its `aria_bindings` record was written manually to
mirror the coordinator's binding step. Separately, campaign `campaign-b80e4ade72ed42ab815f977b62f8a297` can never
publish: an operator invocation whose telemetry worker failed to start still wrote the immutable
`aria_publish_intents` record, and `publish_campaign` refuses any campaign with a prior intent. That campaign also
terminated ERROR, and the cause is now established: the local world simulator had stopped. It made 8 Explorer
selections but ran only 7 episodes, and died 5 seconds after the last one ended, which is the 8th episode
failing to create a world. A later campaign reproduced the same signature exactly, erroring after a single
successful Explorer call with zero episodes while nothing was listening on the simulator port. The earlier
attribution to the Aria completion path was wrong. The generic handler in `_execute` discards the traceback,
so an infrastructure outage is indistinguishable from a logic fault in the recorded state; that reporting gap
is a real limitation of this prototype.

Three repeated trials and four challenge schedules are finite observations, not statistical certainty or an unbreakable policy. A reduced incident is only locally minimal in the tested finite neighborhood. The evidence-gap diagnostic is limited to its two worlds, ten public probes and declared deadline; it does not prove universal impossibility.

Verified remote readback is mandatory before development evidence enters model optimization. Local storage and pending outbox uploads keep incidents inspectable during outages but do not clear the sponsor gate. Aria output is advisory; manual UI capture is attributed operator evidence, distinct from independently verified remote data. A manually started Aria chat does not satisfy automatic invocation.

Campaign spend admission reserves the worst allowed input/output tokens at operator-verified rates for the exact frozen model. V4 uses 32,000 input and 2,000 output tokens, a 20-second request timeout and no automatic retry. Its $0.04984 call allowance and $53.02976 reserve for 1,064 protected calls can limit development before the 6,000-call or 204-million-token ceilings; $500 is the authorized per-campaign cap ceiling, raised from $100 on operator authorization; the 2026-09-13 split-role campaigns ran under a $400 cap. These allowances are not billed totals. Missing prices block full live campaign admission. Actual provider usage and billing may be unavailable and remain unknown in reports. Verify credited account and current rates before enabling live execution.

The external integration preserves independently authored agent logic through a reviewed adapter. Source review and offline compatibility are separate from the six-case repeated transfer experiment. Internal smoke fixtures cannot satisfy external acceptance. Final/external evidence cannot be fed back into the same development campaign.

Pre-existing work: the original repository (now public by owner choice), React/Vite and FastAPI scaffold, health endpoint, configuration and opt-in provider checks. New implementation: simulator, fixed oracle, agent loop/overlay, experiment gates, evidence storage, sponsor adapters, regression integration, dashboard and verification. Reused libraries and pinned source provenance are recorded in dependency locks and external-agent documentation.
