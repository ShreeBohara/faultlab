_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW - native adapter v2 (smolagents-toolcalling-v2), 2026-09-29. Cost $0. I made no provider, model, W&B, Weave or outside network call. I changed no product file. No git command touched the index or HEAD. Saved run stores were read only (mode=ro&immutable=1). The harness refused a REPORT.md from this subagent, so the full report is this text. Evidence files are in /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/review-product/.

VERDICT: An operator can use v2 from start to finish offline. I did every step myself: register v2 (API and CLI), see it in the real dashboard, plan a baseline, run a baseline study, plan and start a Learn campaign with discovery v3 history, Stop, retry evidence, export and import a bundle, and read the recording. All of it worked. v1 and the reference Actor still work as before. The frozen identities are unchanged. I found one MEDIUM issue (M1): v2 decodes a short label the agent was never shown. That lets a guessed citation become valid, which v1 could never produce. Decide it before the first live v2 run. I also found four LOW issues about docs and messages.

WHAT I RAN (all offline)
- Full backend suite: 2816 passed, 180 skipped, 0 failed (1060 s), the same count as the builder (backend-full-pytest.log).
- Frontend vitest: 334 passed in 22 files (frontend-vitest.log).
- tsc --noEmit: passed. I did not build, so dist/ stayed unchanged (frontend-typecheck.log).
- Playwright fixture suite: 17 passed, 1 opt-in skip. Results went to playwright-results/, not to frontend/tests/.results.
- My 24 product probes all passed (test_review_native_v2.py, review-probes-pytest.log, review_probes.out.json). They use real smolagents, the real runner, ledger, store and API. Only the model transport is scripted.
- Real dashboard walk-through: every step passed, with 0 page errors and 0 non-local requests. The only console error was a /favicon.ico 404 (dashboard_walkthrough.mjs, dashboard-walkthrough.out.json, dashboard-01..05 screenshots). Setup:
  - The real Vite server and the real FastAPI backend and coordinator (serve_offline_backend.py), with no page.route mocks.
  - The model transport and evidence reader were the repository's declared offline replacements.
  - The backend refused any read of .env and any non-loopback socket.

ITEM 1: register, see, plan, start
- API registration:
  - POST /api/agent-registrations {agent:smolagents-v2} returned 201 with id smolagents-1.26.0-adapter-v2-… and the full v2 name.
  - The same request again also returned 201 with the same registration, so a double click is harmless.
  - Run options then showed v2 registered and v1 not registered.
- CLI registration, the real `regressions register --agent smolagents-v2` code path:
  - With no backend running, it fell back to the offline store (exit 0), and the dashboard row then showed registered.
  - With a loopback backend running, it registered through the API and returned the same id.
  - An unknown agent is refused with a plain argparse message.
- Real dashboard:
  - The agent list is: reference, v1, and "smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)". The v2 note appears when v2 is chosen.
  - Register saved the registration.
  - A dev-6 baseline plan showed the v2 name and registration. Start completed (Safe unresolved).
  - For Learn, the two pre-check protocols are disabled for v2. A v3-history plan showed "No prior history". Start, then Stop, ended STOPPED.
- Start's own pre-check (validate_core_configuration) accepted the v2 baseline, Learn v1 and Learn v3 plans.
  - The history check says CURRENT, and readiness is ready with provider_calls 0.
  - These are refused with clear 409 messages: v2-reachability and v3-history-reachability for v2, and compare without an accepted policy.
- Baseline study to v3 history is v2's own:
  - The v2 baseline study ran through the API: 36 trials, of which 18 B0 were all on v2 and 18 B1 made 0 model calls.
  - All B0 evidence was weave-verified (in-memory double), and all 18 reports cited obs-N labels.
  - The v2 v3 plan froze exactly those 18 episodes: episode_ids_hash matches, and the build row shows adapter hash 34878663f626.
  - A v1 v3 plan in the same store got NO_PRIOR_HISTORY.
  - Starting the v2 v3 campaign ran the full loop to ACCEPTED. Its discovery request carried exactly the frozen v2 summary (probe 3).
- Real saved store: a private copy of FaultLab_Runs/2026-09-29/native-learn-v3 (its WAL was empty), opened by this runtime.
  - Both saved campaigns still read: plan 200 and recording 200.
  - The old v1 registration is refused.
  - Registered again, v1's v3 history keeps the 22 verified saved v1 episodes.
  - A v2 v3 plan gets NO_PRIOR_HISTORY, so v2 never borrows v1's history (probe 8c).
- v1 and reference still work:
  - v1 registered, planned, started and completed. Its report_submitted payload is still only {report}.
  - The offline reference smoke completed.
  - The reference Learn plan with discovery v2 was accepted.

ITEM 2: runtime behaviour in scripted episodes
- Labels in every observation path and decode before validation: the builder's tests cover this and passed in the full suite. The events API and the recording show raw and decoded citations.
- Final turn and step alignment: when the agent never reports, v1 and v2 both send exactly 8 requests, and only the 8th is flagged final. For v2 that request offers only final_answer with response_contract native_final_answer. There is no 9th request (probe 6a). A valid final-turn report is recorded with final_report_required true and the native contract (6c).
- Malformed or forbidden final-turn output: I tried five (non-JSON, schema-invalid, extra argument, business call, answer not an object). v1 and v2 behave identically: 8 requests, 7 HTTP attempts (the business call was not dispatched), no report_submitted, ActorReportError. Nothing is repaired (6b).
- Ledger and transport retry parity: the builder's tests passed (5 charged calls, 1 retry event, cost unknown, both adapters).
- Stop mid-episode: the v2 Learn campaign ended STOPPED with its episode INTERRUPTED (probe 4), and Stop also worked in the dashboard.
- Provider identity mismatch: v1 and v2 both fail after 1 request, with 1 provider-failure record and unknown cost (6e).
- Evidence retry: a v2 episode whose first read failed was verified by retry_evidence, with 0 model calls. The verified report equals the decoded report (probe 5).
- Full Learn loop on v2: all 7 phases ran on v2 only. Accepted mode reached ACCEPTED and compare completed, and the accepted policy is offered only to v2. Rejected mode reached NO_CHANGE.

ITEM 3: recording and export
- report_submitted records the raw tokens, decoded IDs, label map, labels shown, adapter id, final-turn flag and contract.
- Bundle import:
  - A bundle exported from a v2 episode imports with the v2 entrypoint and cited labels in its recording.
  - v1, v2 and reference are all offered as targets, and a rerun on v1 completed.
  - After the v2 module changes, the v2 target is refused with "register this agent again, then refresh the review" (probe 7b).
- Portability from v1 to v2 is refused, which is correct because they share the same source.
- check_clock_drift_native.py and check_clock_drift.py both exit 0 on a v2 store (drifted 0). v2 is correctly left out of the old tick-0 rule.
- The history summary names v2 and lists its build.

ITEM 4: failure modes
- Old v1 registration:
  - The v1 adapter hash moved from 61497db3… to fa7a58db… only because registry.py changed. external_agent.py (sha 6c0909bf…) and the v1 prompt hash 2251542869cf… are unchanged.
  - Every v1 registration must be made again. The dashboard shows "Not registered for this setup" with a Register button.
  - Planning with the old id gives a clear message: "Register the current reviewed agent before creating a live campaign".
  - Starting an old idle plan says "Current source, model or campaign limits differ from the saved plan" (see L4). Saved plans stay readable.
- v2 plan on a runtime without v2 (simulated): the plan read and Start both give 409 "…missing, corrupt or inconsistent; execution is blocked". Lists still load, and there are no provider calls (L2).
- Malformed final-turn output: see item 2.

ITEM 5: docs
- docs/external-agent-setup.md (the v2 section) is accurate and plain. I checked every claim.
- The gaps are L1 and L3.

FROZEN IDENTITIES (recomputed)
- Unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c.
- v2 prompt hash is 19a24312…, v2 adapter hash is 34878663….
- No file under referee/, simulator/, contracts/, promotion.py, challenge.py or evaluation.py was modified today.
- The saved store kept its size and modification time.

LIMITS OF THIS REVIEW
- Offline only: this says nothing about how a real model responds to labels or to the strict final turn.
- The runtime without v2 was simulated. I did not check out an older commit.
- In the dashboard walk-through, episodes carry the offline-fixture source label, so they show "Offline reference smoke" provenance. That label comes from the test runner, not from v2.
- I did not rerun the builder's mutation checks.
- The builder's REPORT.md was not available to me. I reviewed the code, tests, docs and artifacts directly.

## Findings (structured)

- **M1 (MEDIUM)** `backend/app/integrations/external_agent_v2.py`: v2 decodes any journal label delivered by the request, including labels the agent was never shown. When the broker retries a failed call internally, both attempts go into the journal. v1's tool result returns only the last attempt (external_agent.py 186-189; broker retry loop business_tools.py 192-226). So the agent sees a numbering gap (obs-1, obs-2, obs-4). A report citing the hidden label (obs-3) is decoded to a real evidence ID it never saw and passes C1-C8. Under v1 such a citation was impossible, because a hidden hex ID cannot be guessed. The reference Actor sees every journal observation, and its code says a label outside the request 'cannot make a guessed citation valid'. So v2 is scored under a slightly looser citation rule than both v1 and the reference Actor. The difference appears in exactly the fault cases FaultLab studies: dev-2, dev-6, and any F1 or F4 recipe. The docs mention neither the gap nor this effect. Evidence: review_probes.out.json '6d_label_gap_broker_retry' (dev-6): the journal holds 4 observations [get_order, update_order, send_confirmation TRANSIENT_UNAVAILABLE, send_confirmation TRANSIENT_UNAVAILABLE], and labels_shown_to_agent is [obs-1, obs-2, obs-4]. '6f_unseen_label_decodes': the report cites obs-1..obs-4. obs_3_decoded_to_real_id is true, episode_report_cites_unseen_observation is true, and C1-C8 all pass. Code: external_agent_v2.py lines 183-188 use delivered = self.request_observations, the whole journal at request time, not self.shown_labels. Fix: Decide before the first live v2 run. Either choice changes adapter_protocol, and so v2's prompt identity and history. Option (a): decode only labels already shown to the agent by that request, so unseen labels pass through and fail as in v1. Option (b): keep the rule, document the gap and its scoring effect in external-agent-setup.md, and record a per-report flag such as 'cited_unshown_labels'.
- **L1 (LOW)** `docs/user-guide.md`: The operator guide does not mention v2, and one sentence in it is now wrong. Lines 21-22 list only 'FaultLab reference Actor or smolagents ToolCallingAgent 1.26.0'. Lines 98-100 say 'The native smolagents adapter makes no retries (at most 24)', but both native adapters now make one charged transport retry. The same guide's line 408 already says the worst case is 48. Evidence: docs/user-guide.md lines 21-22 and 98-100. backend/app/integrations/external_agent.py lines 124-152 contain the retry, which v2 reuses. Only docs/external-agent-setup.md and docs/regression-runner.md mention v2. Fix: Name adapter v2 in the Reviewed agent choice and link to external-agent-setup.md. Correct lines 98-100 to say the native adapters can also make one charged transport retry per turn, with a worst case of 48.
- **L2 (LOW)** `docs/external-agent-setup.md`: A store holding v2 plans, when opened by the pre-v2 runtime, reports those valid plans as 'missing, corrupt or inconsistent'. The old code cannot be changed, and nothing warns the operator about this. Evidence: review_probes.out.json '8a_v2_plan_on_runtime_without_v2' (simulated by narrowing SavedRunPlan.agent to the pre-v2 literal and removing v2 from the registry maps): GET /plan and POST /start both return 409 'Saved campaign plan is missing, corrupt or inconsistent; execution is blocked'. The campaign and registration lists still load, and there are 0 provider calls. Fix: Add one sentence to the v2 section: stores that contain v2 plans need this runtime or later, and an older checkout will call them corrupt but will not change them.
- **L3 (LOW)** `CURRENT_STATUS.md`: The status page is not updated for v2. It still names current code 5583dcad… and does not tell operators that every v1 registration must be made again, because the v1 adapter hash moved when registry.py changed. Evidence: CURRENT_STATUS.md line 13 says 'current code is 5583dcad…'. builder/identity-after.json shows runtime_hash 7968b622… and native_v1_adapter_hash fa7a58db… (before: 61497db3…). Probe 8c: the real saved v1 registration is refused after the change. Fix: At commit time (PM), update the current runtime and identities. Add 'register v1 again after this change' and a short v2 entry that links to external-agent-setup.md.
- **L4 (LOW)** `backend/app/lab/run_plans.py`: This is not new with v2, but v2 triggers it for every existing v1 user. Starting an idle plan saved before a runtime change fails with 'Current source, model or campaign limits differ from the saved plan', and the message does not give the next step. The planning path's message does give the next step. Evidence: review_probes.out.json '8b_old_v1_registration_after_runtime_change': POST /start returns 409 'Current source, model or campaign limits differ from the saved plan', and planning with the old id returns 409 'Register the current reviewed agent before creating a live campaign'. The message comes from run_plans.validate_run_plan (around line 636). Fix: Optional: append 'register the agent again and create a new campaign; the saved plan stays readable' to the Start refusal.
