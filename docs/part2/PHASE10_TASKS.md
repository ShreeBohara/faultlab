# Phase 10 progress

Protocol: [PHASE10_EXPERIMENT.md](PHASE10_EXPERIMENT.md). Results: [PHASE10_RESULTS.md](PHASE10_RESULTS.md).
Checked means done and verified, not planned.

## Before any paid call

- [x] Found the mechanism for free, from retained data: `scripts/experiments/analyze_citations.py` classified every citation in 466 completion-study reports and found **15 (3.22%)** cite an evidence ID that does not exist — characters dropped, or a word fragment spliced into the hex.
- [x] Declared the protocol: replay T15's policy through the frozen validation batch, primary read-out, scored/replaced rule, interpretation bands, attempt cap and spend guard, all before spending.
- [x] Built replay mode **inside** the completion study rather than as a parallel harness, so it reuses the unchanged `execute_slots` and `assess_pairs` and cannot drift from the gate it is measuring.
- [x] Ran a five-lens adversarial review with a refutation pass before any paid call: 41 findings, **22 confirmed**.

## What the review caught, and the fixes

- [x] **The declared interpretation bands were unreachable at n = 10** — at 8 of 10 the Wilson lower bound is 0.49, which supports nothing. n was raised to 20 scored replays rather than the claims weakened.
- [x] **The read-out denominator disagreed between protocol and runner**, and a failed replay shrank it in the favourable direction. Declared rule added: a replay producing no validation assessment observed nothing, and is retained, reported and replaced.
- [x] **The runner pinned the Mechanic model, which replay never calls, and never pinned the Actor**, which produces every episode. `EXPECTED_ACTOR` is now verified before every replay.
- [x] **The dashboard rejected every replay study record as malformed** — 828 paid episodes could not have been watched. `frontend/src/completion.ts` now accepts a replay's empty candidate list and `replay_policy_hash`, while an ordinary study with no candidates is still malformed, with tests for both.
- [x] **A campaign created whose study then failed to start escaped the spend guard** — the same defect class Phase 9's review found, reintroduced by adapting that runner. Campaigns are now registered before polling.
- [x] **Nothing verified the started study was actually a replay.** The runner now aborts unless the backend echoes `replay_of`.
- [x] Added an end-to-end HTTP replay test, verdict assertions, a `content=None` guard, and a test that replay cannot accept, activate or rewrite a policy decision.
- [x] 562 backend tests, 124 frontend tests, build and 3 browser fixtures green. Only `algorithm_hash` and the derived `runtime_hash` moved.

## The run

- [x] 26 attempts (declared cap), **13 scored**, 13 unscored and replaced, 828 live episodes, **$93.82010**.
- [x] **Primary read-out: 0 of 13 scored replays returned `OBSERVED_IMPROVEMENT`. Wilson 95% [0.000, 0.228].**
- [x] Stopped at the declared cap with fewer scored replays than the 20 targeted. Reported the shortfall; did not raise the cap to reach the number.
- [x] T15's policy is still `REJECTED`; no policy is ACCEPTED anywhere.

## Findings recorded

- [x] **The violations are the Actor's, not the policy's**: L arm 26/414 (6.3%) against B0 21/414 (5.1%) — about 1.2 points of excess. Phase 9's 16–28% figure was source-case only and did not generalise.
- [x] **62% of violating episodes (29 of 47) cited a fabricated evidence ID.**
- [x] The token **"extremely" has now been spliced into a hex identifier four separate times** across Phases 8–10, alongside identifiers with 30–31 hex characters where a real one has 32. A reproducible decoding artifact, not random noise.
- [x] The failure concentrates where there is most to transcribe: `notification-18` cites 13–14 of 15 observations and is the worst case in **both** arms (12/50 L, 7/50 B0).
- [x] **`notification-18` fails reproducibly**, answering the question that started the phase.
- [x] The arithmetic is consistent: 6.3% per episode implies a 21-episode arm is clean 25.6% of the time; with 8 of 13 batches having exact valid pairs, predicted pass rate ≈ 16% and P(0 in 13) ≈ 11%.
- [x] **A second limitation, equally expensive**: one transient provider timeout makes an episode `LAB_ERROR`, the evidence gateway refuses it, and the whole 42-episode batch aborts. 13 of 26 attempts died this way; only 8 of 26 produced a clean quality verdict.
- [x] Recorded honestly that an intermittent full-suite test failure (~1 in 8 runs, pre-existing, in the untriggered-control path) was investigated and **not** resolved.
- [x] Reconciled cost and updated results, limitations, memory and the central checklist.
